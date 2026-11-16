# this_file: tests/glyphsapp_doubles.py
"""Pure in-memory Glyphs host bridge double; records calls, answers dialogs.

Strict where a native bridge would be: removing an unknown or already removed
token raises, so a facade that double-removes fails its tests.
"""

from itertools import count


class FakeGlyphsBridge:
    def __init__(self, language="en", version=(3.2, 3234.0), version_string="3.2"):
        self.language = language
        self.version = version
        self.version_text = version_string
        self.calls: list[tuple] = []
        self.answers: dict[str, object] = {}
        self.subscriptions: dict[str, tuple[str, object]] = {}
        self.removed: list[str] = []
        self._serial = count(1)

    def _record(self, name, *args):
        self.calls.append((name, *args))
        return self.answers.get(name)

    def ui_language(self) -> str:
        return self.language

    def version_number(self) -> float:
        return self.version[0]

    def version_string(self) -> str:
        return self.version_text

    def build_number(self) -> float:
        return self.version[1]

    def show_macro_window(self) -> None:
        self._record("show_macro_window")

    def clear_log(self) -> None:
        self._record("clear_log")

    def show_notification(self, title, message) -> None:
        self._record("show_notification", title, message)

    def redraw(self) -> None:
        self._record("redraw")

    @property
    def has_callbacks(self) -> bool:
        return bool(self.subscriptions)

    def message(self, message, title, ok_button):
        return self._record("message", message, title, ok_button)

    def ask_string(self, message, value, title, ok_button, placeholder):
        return self._record("ask_string", message, value, title, ok_button, placeholder)

    def get_folder(self, message, allows_multiple, path):
        return self._record("get_folder", message, allows_multiple, path)

    def get_open_file(self, message, title, allows_multiple, filetypes, path):
        args = (message, title, allows_multiple, filetypes, path)
        return self._record("get_open_file", *args)

    def get_save_file(self, message, proposed_file_name, filetypes):
        return self._record("get_save_file", message, proposed_file_name, filetypes)

    def subscribe(self, event, callback) -> str:
        token = f"token-{next(self._serial)}"
        self.subscriptions[token] = (event, callback)
        return token

    def remove(self, token) -> None:
        if token not in self.subscriptions:
            raise KeyError(f"unknown or already removed token: {token}")
        del self.subscriptions[token]
        self.removed.append(token)

    def fire(self, event, *args) -> int:
        """Invoke every live subscription for ``event``; return how many ran."""
        live = [cb for ev, cb in list(self.subscriptions.values()) if ev == event]
        for callback in live:
            callback(*args)
        return len(live)
