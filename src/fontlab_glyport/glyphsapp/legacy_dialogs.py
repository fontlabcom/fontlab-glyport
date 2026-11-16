# this_file: src/fontlab_glyport/glyphsapp/legacy_dialogs.py
"""Only RoboFab's documented legacy AskString import, via the host dialog bridge."""

import sys
from weakref import WeakSet

from ..execution import placeholder
from . import _message_dialogs

_MODULES = WeakSet()
_NAMES = (
    "robofab",
    "robofab.interface",
    "robofab.interface.all",
    "robofab.interface.all.dialogs",
)


def check_legacy_collisions():
    """Check again before cached imports; another host may have loaded since."""
    collisions = sorted(
        key
        for key, module in sys.modules.copy().items()
        if key.split(".")[0] == "robofab" and module not in _MODULES
    )
    if collisions:
        raise ImportError("Compatibility module collision: " + ", ".join(collisions))


def legacy_dialog_providers(bridge):
    """Build scoped providers; refuse any foreign imported RoboFab family."""
    ask_string = _message_dialogs(bridge)["AskString"]

    def AskString(message, value="", title="RoboFab"):
        return ask_string(message, value, title)

    def make(name):
        check_legacy_collisions()
        module = placeholder(name)
        module.__all__ = []
        if name == _NAMES[-1]:
            module.AskString = AskString
            module.__all__ = ["AskString"]
        _MODULES.add(module)
        return module

    return {name: lambda name=name: make(name) for name in _NAMES}
