# this_file: src/fontlab_glyport/glyphsapp/bridge.py
"""The one host boundary of the GlyphsApp facade (planned R026 operations).

``fontlab_bridge.FontLabGlyphsBridge`` implements it for FontLab 9 (natively
unverified); tests also use a pure in-memory double. ``subscribe``/``remove``
are the R026 planned bridge
operations; the rest are the host services this slice needs. Tokens returned
by ``subscribe`` are opaque, unique and removed exactly once by the facade;
the facade keeps a token whose ``remove`` raised, so a retry can remove it.

The callable passed to ``subscribe`` catches the script callback's exceptions
and hands them to the facade's ``error_sink``. If ``error_sink`` itself raises,
that exception propagates into the host's dispatch; a native bridge must
contain it there (log it, keep the GUI thread alive).
"""

from collections.abc import Callable, Sequence
from typing import Protocol


class GlyphsBridge(Protocol):
    """Host services behind ``Glyphs.*`` and the GlyphsApp dialog functions."""

    def ui_language(self) -> str: ...
    def version_number(self) -> float: ...
    def version_string(self) -> str: ...
    def build_number(self) -> float: ...
    def show_macro_window(self) -> None: ...
    def clear_log(self) -> None: ...
    def show_notification(self, title: str, message: str) -> None: ...
    def redraw(self) -> None: ...
    @property
    def has_callbacks(self) -> bool: ...
    def subscribe(self, event: str, callback: Callable[..., None]) -> object: ...
    def remove(self, token: object) -> None: ...
    def message(self, message: str, title: str, ok_button: str | None) -> object: ...
    def ask_string(
        self,
        message: str,
        value: str | None,
        title: str,
        ok_button: str | None,
        placeholder: str | None,
    ) -> str | None: ...
    def get_folder(
        self, message: str | None, allows_multiple: bool, path: str | None
    ) -> str | Sequence[str] | None: ...
    def get_open_file(
        self,
        message: str | None,
        title: str | None,
        allows_multiple: bool,
        filetypes: Sequence[str] | None,
        path: str | None,
    ) -> str | Sequence[str] | None: ...
    def get_save_file(
        self,
        message: str | None,
        proposed_file_name: str | None,
        filetypes: Sequence[str] | None,
    ) -> str | None: ...
