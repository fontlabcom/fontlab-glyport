# this_file: src/fontlab_glyport/ui/cocoa_alert.py
"""NSAlert with injected answers, optional modal Qt, and retained accessories."""

import fontlabapp.qt.dialogs as _qt_dialogs

from .cocoa import NSObject, unsupported

_MISSING = object()


def alert_class(qt, button_class, *, answers, interactive=False):
    class NSAlert(NSObject):
        def init(self):
            self._message, self._informative, self._style = "", "", 1
            self._buttons, self._accessory = [], None
            return self

        def setMessageText_(self, value):
            if value is None:
                raise TypeError("Message text cannot be None")
            self._message = str(value)

        def messageText(self):
            return self._message

        def setInformativeText_(self, value):
            self._informative = str(value or "")

        def informativeText(self):
            return self._informative

        def setAlertStyle_(self, value):
            if int(value) not in (0, 1, 2):
                raise ValueError("Invalid NSAlert style")
            self._style = int(value)

        def alertStyle(self):
            return self._style

        def addButtonWithTitle_(self, title):
            button = button_class.alloc().init()
            button.setTitle_(str(title))
            self._buttons.append(button)
            return button

        def buttons(self):
            from ..foundation import NSArray

            return NSArray(self._buttons)

        def setAccessoryView_(self, value):
            self._accessory = value

        def accessoryView(self):
            return self._accessory

        def runModal(self):
            if "alerts" in answers:
                queue = answers["alerts"]
                if not isinstance(queue, list):
                    raise TypeError(
                        "Injected alerts must be a list of [button title, accessory text]"
                    )
                if not queue:
                    raise unsupported("NSAlert.runModal")
                entry = queue[0]
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    raise ValueError(
                        "An injected alert answer needs a button title and accessory text"
                    )
                title, text = entry
                titles = [button.title() for button in self._buttons] or ["OK"]
                if title not in titles:
                    raise ValueError(
                        f"Injected NSAlert button {title!r} is not present"
                    )
                if self._accessory is not None:
                    self._accessory.setStringValue_(text)
                queue.pop(0)
                return 1000 + titles.index(title)
            answer = answers.get("alert", _MISSING)
            if answer is not _MISSING:
                result = answer(self) if callable(answer) else answer
                result = int(result)
                if 0 <= result < max(1, len(self._buttons)):
                    result += 1000
                if not 1000 <= result < 1000 + max(1, len(self._buttons)):
                    raise ValueError("Injected NSAlert answer is not a button")
                return result
            if not interactive:
                raise unsupported("NSAlert.runModal")
            return self._modal()

        def _modal(self):
            from ..plugins.fontlab_host import qt_widget

            if not self._buttons:
                self.addButtonWithTitle_("OK")
            widgets = [button._qt for button in self._buttons]
            accessory = None if self._accessory is None else qt_widget(self._accessory)
            kinds = ("Warning", "Information", "Critical")
            box = _qt_dialogs.create_message_box(
                qt.QtGui, self._message, self._informative, kinds[self._style]
            )
            index = _qt_dialogs.run_button_message_box(box, widgets, accessory)
            return 1000 + (index if index is not None else 0)

    return NSAlert
