# this_file: tests/test_cov_plugins_host.py
"""Coverage for the plugin host contract (R026): constants, re-exports, Protocol stubs."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from fontlab_glyport.plugins import host as host_module
from fontlab_glyport.plugins.host import (
    AFTER_NATIVE_LAYER,
    BEFORE_NATIVE_LAYER,
    LAYER_FILTERS,
    MENUS,
    PaintContext,
    PluginHost,
)

# Every operation of the contract, with arguments that satisfy its signature.
_STUB_CALLS: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {
    "register_menu": (("EDIT_MENU", object()), {}),
    "register_panel": ((object(), "Title", 10, 20), {}),
    "register_tool": ((object(),), {}),
    "register_painter": ((BEFORE_NATIVE_LAYER, lambda ctx: None), {"layer_filter": "all"}),
    "register_file_format": ((object(),), {"guard": None}),
    "remove": ((object(),), {}),
    "selected_layers": ((), {}),
    "current_font": ((), {}),
    "snapshot_layer": ((object(),), {}),
    "restore_layer": ((object(), object()), {}),
    "undo_group": (("name",), {}),
    "run_dialog": ((object(), "T", "Apply", lambda ok: None), {}),
    "redraw": ((), {}),
    "notify": (("title", "message"), {}),
}


def test_menus_when_listed_then_contains_ten_unique_glyphs_menu_names() -> None:
    """MENUS carries the ten Glyphs menu constants, each unique and upper-case."""
    assert len(MENUS) == 10, f"expected 10 menus, got {MENUS}"
    assert len(set(MENUS)) == len(MENUS), "menu names must be unique"
    assert all(name.endswith("_MENU") and name.isupper() for name in MENUS), MENUS


def test_reexports_when_imported_then_match_editor_painters_contract() -> None:
    """The painter phase constants are re-exported with their documented values."""
    # These pin the public contract: scripts rely on the constant values as public API.
    assert BEFORE_NATIVE_LAYER == "before_native_layer", "public API: before-layer phase value is stable"
    assert AFTER_NATIVE_LAYER == "after_native_layer", "public API: after-layer phase value is stable"
    assert set(LAYER_FILTERS) == {
        "active",
        "inactive",
        "all",
    }, "public API: layer filter names are stable"
    assert inspect.isclass(PaintContext), "PaintContext must be re-exported as a class"
    assert host_module.PaintContext is PaintContext, "host re-exports the same PaintContext class"


def test_pluginhost_when_inspected_then_declares_every_stub_operation() -> None:
    """The Protocol exposes exactly the operations the loader relies on."""
    declared = {
        name
        for name, member in vars(PluginHost).items()
        if callable(member) and not name.startswith("_")
    }
    assert declared == set(_STUB_CALLS), f"contract drifted: {declared ^ set(_STUB_CALLS)}"


@pytest.mark.parametrize("name", sorted(_STUB_CALLS))
def test_pluginhost_stub_when_called_unbound_then_returns_none(name: str) -> None:
    """Protocol bodies are bare ``...``; calling them unbound yields None.

    These pin the public contract: the bodies are no-op defaults a host may inherit.
    """
    args, kwargs = _STUB_CALLS[name]
    method = getattr(PluginHost, name)
    result = method(None, *args, **kwargs)
    assert result is None, f"{name} stub should return None, got {result!r}"


def test_pluginhost_has_callbacks_when_read_unbound_then_returns_none() -> None:
    """The ``has_callbacks`` property stub has an ellipsis body."""
    getter = PluginHost.has_callbacks.fget
    assert getter is not None, "has_callbacks must be a property"
    assert getter(None) is None, "property stub body is a bare ellipsis"


def test_pluginhost_when_subclassed_then_concrete_host_satisfies_contract() -> None:
    """A minimal concrete host can implement the Protocol and be instantiated."""

    class _Host(PluginHost):
        reporter_background_phase = AFTER_NATIVE_LAYER

        @property
        def has_callbacks(self) -> bool:
            return True

    host = _Host()
    assert host.has_callbacks is True, "subclass property must override the stub"
    assert (
        host.reporter_background_phase == AFTER_NATIVE_LAYER
    ), "subclass attribute overrides the Protocol default"
