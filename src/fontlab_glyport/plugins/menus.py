# this_file: src/fontlab_glyport/plugins/menus.py
"""``Glyphs.menu[EDIT_MENU].append(item)`` routed to a plugin host (R025/R027).

Corpus: 47 ``Glyphs.menu[...].append``/``insert`` calls (WINDOW 16, EDIT 9,
VIEW 7, GLYPH 7, FILE 4, PATH 1, FILTER 1). Every registration keeps its host
token, so ``close()`` removes exactly what this proxy added (unload, context
close); a second ``close()`` does nothing.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from ..errors import UnsupportedCapability
from .host import MENUS, PluginHost


class _HostMenu:
    """One Glyphs main menu; ``append``/``insert`` register items with the host."""

    def __init__(self, owner: "AppMenu", name: str):
        self._owner, self._name = owner, name

    def append(self, item: Any) -> None:
        self._owner._register(self._name, item, None)

    def insert(self, index: int, item: Any) -> None:
        self._owner._register(self._name, item, int(index))

    def __repr__(self) -> str:
        return f"<Glyphs menu {self._name}>"


class AppMenu:
    """The ``Glyphs.menu`` proxy: keys are the GlyphsApp ``*_MENU`` constants."""

    def __init__(self, host: PluginHost, *, wrap: Callable | None = None):
        """``wrap`` (e.g. ``ExecutionContext.wrap``) runs every item's callback."""
        self._host, self._wrap = host, wrap
        self._tokens: list[object] = []
        self._collectors: list[list[object]] = []
        self._runners: list[Callable] = []  # the running plugin's guarded runner

    def __getitem__(self, key: Any) -> _HostMenu:
        if isinstance(key, int) and not isinstance(key, bool):
            capability = "Glyphs.menu.index"
            raise UnsupportedCapability(
                f"Unsupported capability: {capability}", capability=capability
            )
        if key not in MENUS:
            raise KeyError(f"No menu item with tag for key: {key}")
        return _HostMenu(self, key)

    def _register(self, menu: str, item: Any, index: int | None) -> None:
        if self._runners:  # registered while a plugin's code runs: its guard
            item._runner = self._runners[-1]
        elif self._wrap is not None:
            item._runner = self._wrap
        token = self._host.register_menu(menu, item, index)
        self._tokens.append(token)
        for collected in self._collectors:
            collected.append(token)

    @contextmanager
    def collect(self) -> Iterator[list[object]]:
        """Collect the tokens registered meanwhile (a plugin's load, R027)."""
        collected: list[object] = []
        self._collectors.append(collected)
        try:
            yield collected
        finally:
            self._collectors.remove(collected)

    @contextmanager
    def owned_by(self, runner: Callable) -> Iterator[None]:
        """Items registered meanwhile run their callbacks through ``runner``
        (``runner(call)`` returns the callable to invoke): the plugin's guard."""
        self._runners.append(runner)
        try:
            yield
        finally:
            self._runners.pop()

    def forget(self, token: object) -> None:
        """A plugin unload removed ``token`` itself; do not remove it again."""
        if token in self._tokens:
            self._tokens.remove(token)

    def close(self) -> None:
        """Remove every item this proxy registered (newest first); re-raise the first failure."""
        failures = []
        while self._tokens:
            token = self._tokens.pop()
            try:
                self._host.remove(token)
            except Exception as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        if failures:
            raise failures[0]
