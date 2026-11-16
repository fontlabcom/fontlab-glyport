# this_file: src/fontlab_glyport/glyphsapp/fontlab_bridge.py
"""FontLab 9 ``GlyphsBridge`` (R026 subscribe/remove, R027 teardown).

Native modules (``fontlab``, ``PythonQt.QtCore``, ``PythonQt.QtGui``) are
imported on first use, never at module import. Each native member used is
listed with its fontlab-echopy stub line in WORK.md (integration task 2).

- Output: script text reaches the context sink (``ExecutionContext.output``).
  ``show_macro_window``/``clear_log`` leave FontLab's Output panel (user
  content) alone unless ``output_panel=True``.
- ``show_notification`` posts a status-bar message; never a modal dialog.
- ``redraw`` calls ``fontlab.UpdateActiveCanvas()``: a view refresh that sends
  no model change notification.
- ``subscribe`` supports ``GSUpdateInterface``: one owned ``QTimer`` polls an
  interface fingerprint and calls subscribers when it changes, with one
  argument (a ``Notification``). Document opened/will-close events connect one
  slot each to FontLab's ``flItems.instance().qobject`` signals
  (``DOCUMENT_SIGNALS``). Other events raise ``UnsupportedCapability``.
- ``remove`` is idempotent for issued tokens (R026); an unknown token raises.
- Drawing callbacks use the editor painters. DrawBackground paints under
  the outlines through the native ``UnderOwner`` painter; on builds without
  native painters it falls back to an overlay (R054), and its registration
  records REPORTER_BACKGROUND_AS_OVERLAY in the owning execution receipt.
"""

import importlib
import traceback
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from itertools import count
from typing import Any

from .._strict import caller_location
from ..drawing.fallbacks import BACKGROUND_AS_OVERLAY
from ..errors import HostUnavailable, UnsupportedCapability
from ..model import Model
from ..model.fontlab_backend import FontLabBackend
from ..plugins.host import AFTER_NATIVE_LAYER, BEFORE_NATIVE_LAYER
from ..profile_versions import PROFILE_VERSIONS, ProfileVersion
from . import fontlab_dialogs as _dialogs
from . import glyphsapp_provider
from .application import EVENT_NAMES
from .defaults import JsonFileStore, default_defaults_path

UPDATE_INTERFACE = EVENT_NAMES["UPDATEINTERFACE"]
DRAW_FOREGROUND = EVENT_NAMES["DRAWFOREGROUND"]
DRAW_BACKGROUND = EVENT_NAMES["DRAWBACKGROUND"]
# Native fact (glyport-model/probe_signals.json): flItems.instance().qobject emits
# packageReaded(flPackage) for new and opened fonts and signalPackageClosed
# (flPackage) when one closes. MCP set_active_font and save_font emitted none of
# packageActivated, fontSelectedID or signalPackageSaved: those stay unsupported.
DOCUMENT_SIGNALS = {
    EVENT_NAMES["DOCUMENTOPENED"]: "packageReaded",
    EVENT_NAMES["DOCUMENTCLOSED"]: "signalPackageClosed",
}
# No FontLab signal for document activation: the poll fires it when the current
# package (the first item of the interface state) changes.
DOCUMENT_ACTIVATED = EVENT_NAMES["DOCUMENTACTIVATED"]
POLL_INTERVAL_MS = 250
NOTICE_TIMEOUT_MS = 5000
Log = Callable[[str], object]


def _import(name: str):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        raise HostUnavailable(f"FontLab native module {name} is unavailable") from error


def interface_state() -> tuple:
    """Current package id and current glyph id: registered objects only.

    Never reads ``flPackage.fgPackage`` (unsafe on unregistered packages).
    """
    workspace = _import("fontlab").flWorkspace.instance()
    package, glyph = workspace.currentPackage, workspace.currentGlyph
    return (
        package.id if package is not None and package.isValid else None,
        glyph.id if glyph is not None and glyph.isValid else None,
    )


def _package_of(state: object) -> object:
    """The current-package part of an interface state."""
    return state[0] if isinstance(state, tuple) and state else state


class Notification:
    """The single argument callbacks receive (NSNotification-like)."""

    def __init__(self, name: str, obj: object = None) -> None:
        self._name, self._object = name, obj

    def name(self) -> str:
        return self._name

    def object(self) -> object:
        """The event's document, or None (UPDATEINTERFACE has no sender)."""
        return self._object


class FontLabGlyphsBridge:
    """Host services for ``make_glyphsapp_module``; use on the GUI thread.

    ``log`` receives bridge diagnostics (contained callback failures, notices
    without a main window). ``answers`` maps dialog names (``message``,
    ``ask_string``, ``get_folder``, ``get_open_file``, ``get_save_file``) to
    injected results; ``interactive=True`` allows modal Qt dialogs.
    ``version`` accepts a complete ``ProfileVersion`` or the older
    (number, build) pair. Custom pairs need ``version_string`` when scripts
    request versionString: a float cannot establish its patch version.
    """

    def __init__(
        self,
        *,
        log: Log,
        version: ProfileVersion | tuple[float, float],
        version_string: str | None = None,
        language: str = "en",
        output_panel: bool = False,
        interactive: bool = False,
        answers: Mapping[str, object] | None = None,
        state: Callable[[], object] = interface_state,
        interval_ms: int = POLL_INTERVAL_MS,
        document: Callable[[object], object] | None = None,
        painters: Callable[[], Any] | None = None,
        paint_scope: Callable[[Any], Any] | None = None,
        diagnostic_sink: Callable | None = None,
    ) -> None:
        self._log, self._version, self._language = log, version, language
        self._version_string = version_string
        self._output_panel, self._state, self._interval = (
            output_panel,
            state,
            interval_ms,
        )
        self._dialogs = _dialogs.Dialogs(
            lambda: _import("PythonQt.QtGui"), interactive, answers or {}
        )
        self._serial = count(1)
        self._issued = 0
        self._subscribers: dict[int, Callable[..., None]] = {}
        self._timer: dict[str, Any] = {}  # "timer", "slot": never attrs on natives
        self._baseline: object = None
        # Nested slot dispatches (a callback causing another signal) share one
        # depth: teardown waits for the outermost dispatch to return.
        self._dispatch_depth = 0
        self._close_requested = False
        self._noted = False
        # Document events: token -> (event, callback); event -> signal + slot.
        self._document = document
        self._events: dict[int, tuple[str, Callable[..., None]]] = {}
        self._signals: dict[str, dict[str, Any]] = {}
        # DRAWFOREGROUND: token -> EditorPainters token (L2 drawing.editor).
        self._painters, self._paint_scope = painters, paint_scope
        self._painter_tokens: dict[int, object] = {}
        self._diagnostic_sink = diagnostic_sink

    @property
    def _firing(self) -> bool:
        return self._dispatch_depth > 0

    @property
    def has_callbacks(self) -> bool:
        return bool(self._subscribers or self._events or self._painter_tokens)

    # Host facts --------------------------------------------------------
    def ui_language(self) -> str:
        return self._language

    def version_number(self) -> float:
        return self._version[0]

    def version_string(self) -> str:
        if self._version_string is not None:
            return self._version_string
        if isinstance(self._version, ProfileVersion):
            return self._version.string
        # Legacy (number, build) callers may match a known complete profile.
        # Otherwise a float cannot establish a patch version; require its text.
        for version in PROFILE_VERSIONS.values():
            if self._version == version[:2]:
                return version.string
        raise UnsupportedCapability(
            "A custom compatibility version needs an explicit version_string",
            capability="Glyphs.versionString",
        )

    def build_number(self) -> float:
        return self._version[1]

    # Output and views --------------------------------------------------
    def _main_window(self):
        return _import("fontlab").MainWindow()

    def _output_window(self):
        window = self._main_window()
        if window is None:
            raise HostUnavailable("FontLab main window is unavailable (Output panel)")
        return window

    def show_macro_window(self) -> None:
        """No-op by default: the context sink is the macro window."""
        if self._output_panel:
            self._output_window().doShowOutputPanel()

    def clear_log(self) -> None:
        """No-op by default: FontLab's Output panel is user content."""
        if self._output_panel:
            self._output_window().doClearOutput()

    def show_notification(self, title: str, message: str) -> None:
        text = f"{title}: {message}" if title else str(message)
        window = self._main_window()
        if window is None:
            self._log(f"[notification] {text}\n")
            return
        window.statusBar().showMessage(text, NOTICE_TIMEOUT_MS)

    def redraw(self) -> None:
        _import("fontlab").UpdateActiveCanvas()

    # Dialogs -----------------------------------------------------------
    def message(self, message, title, ok_button):
        return self._dialogs.message(message, title, ok_button)

    def ask_string(self, message, value, title, ok_button, placeholder):
        return self._dialogs.ask_string(message, value, title, ok_button, placeholder)

    def get_folder(self, message, allows_multiple, path):
        return self._dialogs.get_folder(message, allows_multiple, path)

    def get_open_file(self, message, title, allows_multiple, filetypes, path):
        args = (message, title, allows_multiple, filetypes, path)
        return self._dialogs.get_open_file(*args)

    def get_save_file(self, message, proposed_file_name, filetypes):
        return self._dialogs.get_save_file(message, proposed_file_name, filetypes)

    # Callbacks ---------------------------------------------------------
    def subscribe(self, event: str, callback: Callable[..., None]) -> int:
        if event == DRAW_FOREGROUND and self._painters is not None:
            return self._subscribe_painter(callback)
        if event == DRAW_BACKGROUND and self._painters is not None:
            if getattr(self._painters(), "supports_before_native", False):
                return self._subscribe_painter(callback, BEFORE_NATIVE_LAYER)
            token = self._subscribe_painter(callback)
            if self._diagnostic_sink is not None:
                self._diagnostic_sink(BACKGROUND_AS_OVERLAY)
            return token
        if event == DOCUMENT_ACTIVATED:
            if not self._timer:
                self._start_timer()
            token = next(self._serial)
            self._issued = token
            self._events[token] = (event, callback)
            return token
        if event in DOCUMENT_SIGNALS:
            if event not in self._signals:
                self._connect(event)
            token = next(self._serial)
            self._issued = token
            self._events[token] = (event, callback)
            return token
        if event != UPDATE_INTERFACE:
            capability = f"Glyphs.addCallback.{event}"
            supported = ", ".join(
                [UPDATE_INTERFACE, DOCUMENT_ACTIVATED, *DOCUMENT_SIGNALS]
            )
            raise UnsupportedCapability(
                f"Unsupported capability: {capability} (FontLab bridge supports "
                f"{supported})",
                capability=capability,
                location=caller_location(),
            )
        if not self._timer:
            self._start_timer()
        self._note_trigger()
        token = next(self._serial)
        self._issued = token
        self._subscribers[token] = callback
        return token

    def remove(self, token: object) -> None:
        if not isinstance(token, int) or not 0 < token <= self._issued:
            raise KeyError(f"unknown callback token: {token!r}")
        if token in self._painter_tokens:
            self._painters().remove(self._painter_tokens[token])
            del self._painter_tokens[token]
            return
        if token in self._events:
            event = self._events[token][0]
            last = sum(e == event for e, _ in self._events.values()) == 1
            if event == DOCUMENT_ACTIVATED:
                if last and not self._subscribers and self._timer and not self._firing:
                    self._stop_timer()  # raises: token kept for a retry
            elif last and not self._firing:
                self._disconnect(event)  # raises: token kept for a retry
            del self._events[token]  # while firing, teardown runs afterwards
            return
        if token not in self._subscribers:
            return  # idempotent (R026)
        if len(self._subscribers) == 1 and self._timer and not self._firing:
            self._stop_timer()  # raises: token kept, so a retry can remove it
        del self._subscribers[token]  # while firing, _fire tears down afterwards

    def _note_trigger(self) -> None:
        if self._noted:
            return
        self._noted = True
        try:
            self._log(
                f"[GlyphsApp bridge] {UPDATE_INTERFACE} fires only when the current "
                "font or glyph changes, narrower than Glyphs (no edits/selection)\n"
            )
        except Exception:  # noqa: BLE001, S110 - a note must not block subscribe
            pass

    def _start_timer(self) -> None:
        timer = _import("PythonQt.QtCore").QTimer()
        slot = self.poll
        timer.timeout.connect(slot)
        self._timer.update(timer=timer, slot=slot)
        self._baseline = self._safe_state()
        timer.start(self._interval)

    def _stop_timer(self) -> None:
        """Disconnect our slot, then stop and delete (AGENTS.md: disconnect first).

        A failed disconnect changes nothing: the timer keeps running and a
        retry can tear it down.
        """
        timer, slot = self._timer["timer"], self._timer["slot"]
        timer.timeout.disconnect(slot)
        self._timer.clear()
        timer.stop()
        timer.deleteLater()

    def _safe_state(self) -> object:
        try:
            return self._state()
        except BaseException:  # noqa: BLE001 - a GUI slot must not raise
            self._report("interface state")
            return self._baseline

    def _report(self, what: str) -> None:
        detail = traceback.format_exc()
        try:
            self._log(f"[GlyphsApp bridge] {what} failed:\n{detail}")
        except BaseException:  # noqa: BLE001, S110 - nowhere left to report
            pass

    def poll(self) -> int:
        """Timer slot: on a fingerprint change call every subscriber once.

        Returns how many ran. Failures, even process exits, are logged here so
        the GUI thread stays alive.
        """
        state = self._safe_state()
        if state == self._baseline:
            return 0
        previous, self._baseline = self._baseline, state
        ran = self._fire()
        if _package_of(state) != _package_of(previous):
            ran += self._fire_activated()
        return ran

    def _fire_activated(self) -> int:
        if not any(e == DOCUMENT_ACTIVATED for e, _ in self._events.values()):
            return 0
        try:
            package = _import("fontlab").flWorkspace.instance().currentPackage
        except BaseException:  # noqa: BLE001 - a GUI slot must not raise
            self._report("current package")
            return 0
        return self._fire_event(DOCUMENT_ACTIVATED, (package,) if package else ())

    def _fire(self) -> int:
        """Call current subscribers; tear the timer down only after the loop.

        Disconnecting or deleting the timer while PythonQt dispatches its
        ``timeout`` into this slot is the PythonQtSignalReceiver crash class
        (AGENTS.md), so ``remove``/``close`` only drop tokens while firing.
        """
        ran = 0
        self._dispatch_depth += 1
        try:
            for token, callback in list(self._subscribers.items()):
                if token not in self._subscribers:
                    continue  # removed by an earlier callback in this round
                ran += 1
                try:
                    callback(Notification(UPDATE_INTERFACE))
                except BaseException:  # noqa: BLE001 - contain at the host boundary
                    self._report(f"{UPDATE_INTERFACE} callback")
        finally:
            self._dispatch_depth -= 1
        if not self._firing:
            self._deferred_teardown()
        return ran

    def _deferred_teardown(self) -> None:
        closing, self._close_requested = self._close_requested, False
        wanted = {event for event, _ in self._events.values()}
        for event in list(self._signals):
            if closing or event not in wanted:
                try:
                    self._disconnect(event)
                except BaseException:  # noqa: BLE001 - a GUI slot must not raise
                    self._report(f"{event} disconnect")
        activation = any(e == DOCUMENT_ACTIVATED for e, _ in self._events.values())
        if not self._timer or ((self._subscribers or activation) and not closing):
            return
        try:
            self._stop_timer()
        except BaseException:  # noqa: BLE001 - a GUI slot must not raise
            self._report("timer teardown")

    # Editor drawing ----------------------------------------------------
    def _subscribe_painter(
        self, callback: Callable[..., None], phase: str = AFTER_NATIVE_LAYER
    ) -> int:
        """DRAWFOREGROUND -> an after-native-layer editor painter (L2 R032);
        DRAWBACKGROUND -> before it on native canvas painters, else after.

        Glyphs calls ``callback(layer, info)``; ``layer`` is the model layer the
        painters' layer_resolver found (None for a glyph outside the model).
        """
        scope = self._paint_scope

        def paint(context) -> None:
            with scope(context) if scope is not None else nullcontext():
                callback(context.layer, {"Scale": context.scale, "Black": False})

        painter_token = self._painters().register(phase, paint)
        token = next(self._serial)
        self._issued = token
        self._painter_tokens[token] = painter_token
        return token

    def _remove_painters(self) -> None:
        failures = []
        for token in list(self._painter_tokens):
            try:
                self._painters().remove(self._painter_tokens.pop(token))
            except Exception as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        if failures:
            raise failures[0]

    # Document events ---------------------------------------------------
    def _connect(self, event: str) -> None:
        qobject = _import("fontlab").flItems.instance().qobject
        signal = getattr(qobject, DOCUMENT_SIGNALS[event])

        def slot(*args):  # one stable plain function per event, for disconnect
            self._fire_event(event, args)

        signal.connect(slot)
        self._signals[event] = {"signal": signal, "slot": slot}

    def _disconnect(self, event: str) -> None:
        """Disconnect our slot; a failure keeps the record so a retry can."""
        record = self._signals[event]
        record["signal"].disconnect(record["slot"])
        del self._signals[event]

    def _document_for(self, args: tuple) -> object:
        if self._document is None or not args:
            return None
        try:
            return self._document(args[0])
        except BaseException:  # noqa: BLE001 - a GUI slot must not raise
            self._report("document lookup")
            return None

    def _fire_event(self, event: str, args: tuple) -> int:
        """Signal slot: call the event's subscribers; teardown after the loop."""
        ran = 0
        self._dispatch_depth += 1
        try:
            document = self._document_for(args)
            for token, (name, callback) in list(self._events.items()):
                if name != event or token not in self._events:
                    continue
                ran += 1
                try:
                    callback(Notification(event, document))
                except BaseException:  # noqa: BLE001 - contain at the host boundary
                    self._report(f"{event} callback")
        finally:
            self._dispatch_depth -= 1
        if not self._firing:
            self._deferred_teardown()
        return ran

    # Teardown (R027) ---------------------------------------------------
    def close(self) -> None:
        """Drop subscribers, stop the timer, close owned dialogs; repeatable.

        Inside the timer slot the timer teardown is deferred to ``_fire``.
        """
        self._subscribers.clear()
        self._events.clear()
        try:
            self._remove_painters()
            if self._firing:
                self._close_requested = True
            else:
                for event in list(self._signals):
                    self._disconnect(event)
                if self._timer:
                    self._stop_timer()
        finally:
            self._dialogs.close()


def fontlab_glyphsapp_provider(
    ctx,
    *,
    version: ProfileVersion | tuple[float, float],
    packages=None,
    defaults=None,
    **options,
) -> Callable:
    """Wire a FontLab ``GlyphsApp`` adapter into ``ExecutionContext`` ``ctx``.

    The model reads ``FontLabBackend(packages)`` (``OwnedPackage`` items from
    ``owned_test_package`` for acceptance). Bridge diagnostics and callback
    errors go to ``ctx.output``; ``ctx.close()`` removes every callback, then
    closes the bridge. ``options`` go to ``FontLabGlyphsBridge``. Use it as
    ``ctx.adapters["GlyphsApp"] = fontlab_glyphsapp_provider(ctx, version=...)``.
    """
    backend = FontLabBackend(packages)
    model = Model(backend)

    def document(package):
        """GSDocument for a document-event package in the model's scope, else None."""
        font_id = backend.font_id_for(package)
        font = None if font_id is None else model.fonts[font_id]
        return None if font is None else font.parent  # one document per font

    bridge = FontLabGlyphsBridge(
        log=ctx.output.write, version=version, document=document, **options
    )
    ctx.on_close(bridge.close)  # older than the facade's hook, so it runs last

    def error_sink(error: Exception, event: object) -> None:
        detail = "".join(traceback.format_exception(error))
        ctx.output.write(f"[GlyphsApp] {event} callback failed:\n{detail}")

    if defaults is None:
        defaults = JsonFileStore(default_defaults_path())
    return glyphsapp_provider(
        model,
        bridge,
        profile=ctx.profile,
        defaults=defaults,
        wrap=ctx.wrap,
        error_sink=error_sink,
        on_close=ctx.on_close,
    )
