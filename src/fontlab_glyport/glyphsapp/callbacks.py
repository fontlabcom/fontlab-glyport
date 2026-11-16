# this_file: src/fontlab_glyport/glyphsapp/callbacks.py
"""Objective-C callback registration over the existing application bridge."""

from ..ui.cocoa import unsupported


def callback_handler(application):
    class GSCallbackHandler:
        @classmethod
        def addCallback_forOperation_(cls, callback, operation):
            if operation == "DrawFontView":
                # FontLab exposes glyph-editor painters, not Font Window cells.
                raise unsupported("GSCallbackHandler.DrawFontView")
            if not callable(callback):
                raise unsupported(f"GSCallbackHandler.{operation}.observer")
            application.addCallback(callback, operation)

        @classmethod
        def removeCallback_forOperation_(cls, callback, operation):
            application.removeCallback(callback, operation)

        @classmethod
        def removeCallback_(cls, callback):
            for registered, operation in tuple(application._tokens):
                if registered == callback:
                    application.removeCallback(callback, operation)

    return GSCallbackHandler
