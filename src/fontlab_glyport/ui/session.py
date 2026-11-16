# this_file: src/fontlab_glyport/ui/session.py
# SPDX-License-Identifier: Apache-2.0
# Moved from App; constructor and lifetime behaviour unchanged.
"""Session that owns Glyport's Qt-backed Vanilla controls, dialogs and windows.

What: `VanillaSession` builds the Vanilla and dialogs namespaces and tracks
every window they open. `close()` tears all of them down.

Why lazy: the factories in `ui.vanilla` and `ui.dialogs` pull in the Cocoa,
Vanilla and NIB chain (about 8k lines). FontLab's `run_python` has a 5 s
deadline. This module therefore imports both factories INSIDE the constructor.
After `import fontlab_glyport.ui.session`, neither PythonQt nor
`fontlab_glyport.ui.vanilla` nor `fontlab_glyport.ui.cocoa` is loaded.

Use: `with VanillaSession() as session: session.vanilla.Window(...)`.
"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, Self


def _raise_callback_error(error: Exception, sender: object) -> None:
    raise error


class VanillaSession:
    """Own adapters and their windows, without replacing installed namespaces.

    Callbacks receive the originating control. Programmatic setters follow
    that adapter's policy (quiet core setters; Tabs selection is reported).
    close() disconnects owned widget signals and is safe to repeat. No
    QApplication or application event loop is constructed. Keep the session
    strongly reachable until explicit close: retention is session-scoped, not
    process-global.
    """

    def __init__(
        self,
        *,
        qt: Any = None,
        error_sink: Callable[[Exception, object], object] = _raise_callback_error,
        interactive_dialogs: bool = True,
    ) -> None:
        from fontlab_glyport.ui.dialogs import make_dialogs_module
        from fontlab_glyport.ui.vanilla import make_vanilla_module

        if qt is None:
            from PythonQt import QtCore, QtGui

            qt = SimpleNamespace(QtCore=QtCore, QtGui=QtGui)
        self._hooks: list[Callable[[], object]] = []
        self._windows: set[Any] = set()
        self._closed = False
        try:
            self.vanilla = make_vanilla_module(
                qt, error_sink=error_sink, settings={}, on_close=self._hooks.append
            )
            self._own_windows()
            self.dialogs = make_dialogs_module(
                qt,
                error_sink=error_sink,
                interactive=interactive_dialogs,
                on_close=self._hooks.append,
            )
        except BaseException:
            self.close()
            raise

    def _own_windows(self) -> None:
        # The underlying environment tracks opened windows. Retain unopened
        # windows too, so early construction exits still disconnect their slots.
        session = self

        def owned(base: type) -> type:
            class OwnedWindow(base):
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    if session._closed:
                        raise RuntimeError("Vanilla session is closed")
                    try:
                        super().__init__(*args, **kwargs)
                    except BaseException:
                        # Glyport can allocate its QWidget before validating
                        # frames/options. Retain failed constructions too;
                        # session.close() owns teardown, never incidental GC.
                        if "_view" in self.__dict__:
                            self._fontport_incomplete = True
                            session._windows.add(self)
                        raise
                    session._windows.add(self)

                def _teardown(self, *, view_closing: bool) -> None:
                    # Glyport routes both close() and native closeEvent here.
                    # Its teardown disconnects children before deleteLater.
                    # Keep the strong owner if teardown raises.
                    if self.__dict__.get("_fontport_incomplete", False):
                        self._closed = True
                        for child in self.__dict__.get("_children", {}).values():
                            child._disconnect()
                        view = self._view
                        if "_owner" in getattr(view, "__dict__", {}):
                            view._owner = None
                        view.deleteLater()
                        self._fontport_incomplete = False
                    else:
                        super()._teardown(view_closing=view_closing)
                    session._windows.discard(self)

                def close(self) -> None:
                    if self.__dict__.get("_fontport_incomplete", False):
                        self._teardown(view_closing=False)
                        return
                    super().close()
                    # Also support factory doubles/adapters with just close().
                    if not hasattr(base, "_teardown"):
                        session._windows.discard(self)

            OwnedWindow.__name__ = base.__name__
            return OwnedWindow

        for name in ("Window", "FloatingWindow", "Sheet"):
            if name in getattr(self.vanilla, "__all__", ()):
                setattr(self.vanilla, name, owned(getattr(self.vanilla, name)))

    def close(self) -> None:
        """Attempt every teardown hook; propagate the first cleanup failure."""
        self._closed = True
        failures = []
        for window in list(self._windows):
            try:
                window.close()
            except BaseException as error:  # noqa: BLE001 - finish cleanup, then re-raise
                failures.append(error)
        while self._hooks:
            try:
                self._hooks.pop()()
            except BaseException as error:  # noqa: BLE001 - finish every hook, then re-raise
                failures.append(error)
        if failures:
            raise failures[0]
        if self._windows:
            raise RuntimeError(
                "Vanilla window teardown did not complete; ownership retained"
            )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()
