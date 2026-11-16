# this_file: src/fontlab_glyport/ui/cocoa_menu.py
"""``NSMenu``/``NSMenuItem`` as plain objects a host turns into QActions (R025).

Supports both construction styles the corpus uses:
``NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "go:", "")``
(50 uses) and GlyphsApp's ``NSMenuItem(title, callback, target=None,
keyboard=None, modifier=0)`` (30 uses). ``fire()`` performs the item: a
Python callable action is called with the item as sender (bound to
``target`` when that is an object owning a method of that name), a selector
string is performed on ``target`` with its colon arity. ``state``,
``enabled``, ``keyEquivalent`` and the modifier mask are kept for the host,
which observes changes through ``changed`` callbacks.
"""

from collections.abc import Callable
from typing import Any

from .._strict import caller_location
from ..errors import UnsupportedCapability
from .cocoa import NSObject, perform

NSOffState, NSOnState, NSMixedState = 0, 1, -1
# NSEventModifierFlags used for key equivalents.
NSShiftKeyMask, NSControlKeyMask = 1 << 17, 1 << 18
NSAlternateKeyMask, NSCommandKeyMask = 1 << 19, 1 << 20


class NSMenu(NSObject):
    """An ordered list of items (a submenu)."""

    def initWithTitle_(self, title):
        self._title, self._items = str(title or ""), []
        return self

    def init(self):
        return self.initWithTitle_("")

    def title(self) -> str:
        return self._title

    def itemArray(self) -> list:
        return list(self._items)

    def numberOfItems(self) -> int:
        return len(self._items)

    def addItem_(self, item) -> None:
        self._items.append(item)

    def insertItem_atIndex_(self, item, index) -> None:
        self._items.insert(int(index), item)

    def removeItem_(self, item) -> None:
        self._items.remove(item)

    def append(self, item) -> None:  # GlyphsApp convenience
        self.addItem_(item)

    def insert(self, index, item) -> None:  # GlyphsApp convenience
        self.insertItem_atIndex_(item, index)


class NSMenuItem(NSObject):
    """A menu command; the host maps it to a QAction and calls ``fire()``.

    ``_runner`` (set by ``plugins.menus.AppMenu``) wraps the callback, e.g. in
    ``ExecutionContext.wrap``.
    """

    _runner = None

    def __init__(
        self, title=None, callback=None, target=None, keyboard=None, modifier=0
    ):
        """GlyphsApp's convenience constructor (``NSMenuItem(title, callback)``)."""
        if title is None and callback is None:
            self.init()  # NSMenuItem(): an empty item, like new()
            return
        if callback is None:
            raise ValueError("callback is required")
        self.initWithTitle_action_keyEquivalent_(title, callback, keyboard or "")
        self._target = target
        self._modifiers = int(modifier or 0)

    @classmethod
    def separatorItem(cls):
        item = cls.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        item._separator = True
        return item

    def initWithTitle_action_keyEquivalent_(self, title, action, key):
        self._title, self._action, self._key = str(title or ""), action, str(key or "")
        self._target, self._modifiers, self._state = None, 0, NSOffState
        self._enabled, self._tag, self._submenu = True, 0, None
        self._separator, self._represented, self._image = False, None, None
        self._observers: list[Callable[[Any], None]] = []
        return self

    def init(self):
        return self.initWithTitle_action_keyEquivalent_("", None, "")

    def _changed(self) -> None:
        for observer in list(self._observers):
            observer(self)

    def title(self) -> str:
        return self._title

    def setAttributedTitle_(self, title) -> None:
        raise UnsupportedCapability(
            "QAction cannot render attributed menu titles",
            capability="NSMenuItem.setAttributedTitle_",
            location=caller_location(),
        )

    def setTitle_(self, title) -> None:
        self._title = str(title or "")
        self._changed()

    def action(self):
        return self._action

    def setAction_(self, action) -> None:
        self._action = action

    def target(self):
        return self._target

    def setTarget_(self, target) -> None:
        self._target = target

    def image(self):
        return self._image

    def setImage_(self, image) -> None:
        """An ``NSImage`` (``ui.images``); the host shows its ``icon()``."""
        self._image = image
        self._changed()

    def keyEquivalent(self) -> str:
        return self._key

    def setKeyEquivalent_(self, key) -> None:
        self._key = str(key or "")
        self._changed()

    def keyEquivalentModifierMask(self) -> int:
        return self._modifiers

    def setKeyEquivalentModifierMask_(self, mask) -> None:
        self._modifiers = int(mask)
        self._changed()

    def state(self) -> int:
        return self._state

    def setState_(self, state) -> None:
        self._state = int(state)
        self._changed()

    def isEnabled(self) -> bool:
        return self._enabled

    def setEnabled_(self, flag) -> None:
        self._enabled = bool(flag)
        self._changed()

    def tag(self) -> int:
        return self._tag

    def setTag_(self, tag) -> None:
        self._tag = int(tag)

    def representedObject(self):
        return self._represented

    def setRepresentedObject_(self, value) -> None:
        self._represented = value

    def isSeparatorItem(self) -> bool:
        return self._separator

    def submenu(self):
        return self._submenu

    def setSubmenu_(self, menu) -> None:
        self._submenu = menu

    def hasSubmenu(self) -> bool:
        return self._submenu is not None

    def append(self, item) -> None:  # GlyphsApp: add to the submenu
        self._submenu.addItem_(item)

    def insert(self, index, item) -> None:  # GlyphsApp: insert into the submenu
        self._submenu.insertItem_atIndex_(item, index)

    def fire(self) -> None:
        """Perform the item's action (the host calls this when triggered)."""
        action, target = self._action, self._target
        if action is None:
            return
        if callable(action) and not isinstance(action, str):
            call = lambda: action(self)
        else:
            name = action.decode() if isinstance(action, bytes) else str(action)
            if target is None:
                raise TypeError(
                    f"menu item {self._title!r}: selector {name} has no target"
                )
            args = (self,) if name.count(":") else ()
            call = lambda: perform(target, name, *args)
        runner = self._runner
        (runner(call) if runner is not None else call)()
