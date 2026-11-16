# this_file: tests/plugin_doubles.py
"""An in-memory plugin host: records registrations, layers are plain lists."""

from contextlib import contextmanager

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.plugins.host import PaintContext


class Layer:
    def __init__(self, name, paths):
        self.name, self.paths = name, list(paths)


class FakeHost:
    def __init__(self, layers=(), unsupported=()):
        self.layers = list(layers)
        self.unsupported = set(unsupported)
        self.registered: dict[int, tuple] = {}
        self.removed: list[int] = []
        self.log: list[tuple] = []
        self.dialogs: list[dict] = []
        self._next = 0

    def _token(self, *entry):
        if entry[0] in self.unsupported:
            raise UnsupportedCapability(f"no {entry[0]}", capability=f"host.{entry[0]}")
        self._next += 1
        self.registered[self._next] = entry
        return self._next

    def register_menu(self, menu, item, index=None):
        return self._token("menu", menu, item, index)

    def register_panel(self, view, title, min_height, max_height):
        return self._token("panel", view, title, min_height, max_height)

    def register_tool(self, tool, *, guard=None, activate=None, deactivate=None):
        return self._token("tool", tool, guard, activate, deactivate)

    def register_painter(
        self, phase, callback, *, document_id=None, layer_filter="active"
    ):
        return self._token("painter", phase, callback, layer_filter)

    def register_file_format(self, file_format, *, guard=None):
        return self._token("file_format", file_format, guard)

    def remove(self, token):
        if token in self.registered:
            entry = self.registered.pop(token)
            self.removed.append(token)
            if entry[0] == "dialog":
                entry[1]["close"](False)  # removing an open dialog cancels it

    def entries(self, kind):
        return [e for e in self.registered.values() if e[0] == kind]

    @property
    def has_callbacks(self) -> bool:
        return bool(self.registered)

    def selected_layers(self):
        return list(self.layers)

    def current_font(self):
        return "font"

    def snapshot_layer(self, layer):
        return list(layer.paths)

    def restore_layer(self, layer, snapshot):
        layer.paths = list(snapshot)

    @contextmanager
    def undo_group(self, name):
        self.log.append(("undo-begin", name))
        try:
            yield
        finally:
            self.log.append(("undo-end", name))

    def run_dialog(self, view, title, apply_label, on_close):
        """``dialog["close"](applied)`` ends the session once, as the host does."""
        dialog = {"view": view, "title": title, "apply": apply_label, "open": True}

        def close(applied):
            if dialog["open"]:
                dialog["open"] = False
                self.registered.pop(dialog["token"], None)
                on_close(applied)

        dialog["close"] = close
        self.dialogs.append(dialog)
        dialog["token"] = self._token("dialog", dialog)
        return dialog["token"]

    def redraw(self):
        self.log.append(("redraw",))

    def notify(self, title, message):
        self.log.append(("notify", title, message))

    def paint(self, phase, layer, scale=2.0, layer_filter="active"):
        """Invoke registered painters like a native paint pass would."""
        for entry in list(self.registered.values()):
            if entry[0] == "painter" and entry[1] == phase and entry[3] == layer_filter:
                entry[2](
                    PaintContext(
                        1,
                        "L",
                        1,
                        layer_filter == "active",
                        phase,
                        None,
                        None,
                        2.0,
                        None,
                        "painter",
                        scale,
                        layer,
                    )
                )
