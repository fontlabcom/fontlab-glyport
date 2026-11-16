# this_file: tests/ui_doubles_session.py
"""Public-constructor session fixture with injected Qt, model and host doubles."""

from types import SimpleNamespace

from glyphsapp_doubles import FakeGlyphsBridge
from ui_doubles import make_qt

from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp.fontlab_session import FontLabSession
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend


class SessionBridge(FakeGlyphsBridge):
    def close(self):
        for token in list(self.subscriptions):
            self.remove(token)


def make_session(root, *, qt=None, fontlab=None, bridge=None):
    ctx = ExecutionContext(root, "glyphs3")
    session = FontLabSession(
        ctx,
        version=(3.2, 3234.0),
        packages=[],
        defaults={},
        qt=qt or make_qt(),
        fontlab=fontlab or SimpleNamespace(MainWindow=lambda: None),
    )
    session.backend = FakeBackend()
    session.model = Model(session.backend)
    session.bridge = bridge or SessionBridge()
    ctx.adapters.update(session.adapters())
    return ctx, session
