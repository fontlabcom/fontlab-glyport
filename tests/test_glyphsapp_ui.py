# this_file: tests/test_glyphsapp_ui.py
"""GlyphsApp.UI.GlyphView (R049 general-plugin, Context Manager)."""

import pytest
from drawing_doubles import PAINTERS, add_drawing
from ui_doubles import make_qt

from fontlab_glyport.drawing import context as gc
from fontlab_glyport.glyphsapp.ui import make_ui_module
from fontlab_glyport.model import GSGlyph, GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.ui.vanilla import make_vanilla_module


def test_glyph_view_when_painted_then_layer_fills_scaled_to_the_metrics():
    errors = []
    vanilla = make_vanilla_module(
        add_drawing(make_qt()), error_sink=lambda e, s: errors.append(e)
    )
    ui = make_ui_module(vanilla)
    font = Model(FakeBackend()).font
    layer = font.glyphs.append(GSGlyph("tri")).layers[0]  # no components
    layer.width = 500
    layer.paths = [GSPath([GSNode((0, 0)), GSNode((500, 0)), GSNode((500, 700))])]
    w = vanilla.Window((200, 100))
    w.view = ui.GlyphView((0, 0, 200, 100), layer=None)
    w.open()
    widget = w.view.getNSView()
    widget.paintEvent(None)  # no layer: background only, no outline
    assert not any(c[0] == "fill" and c[1] for c in PAINTERS[-1].calls[1:])
    updates = []
    widget.update = lambda: updates.append(True)  # QWidget.update (not in the double)
    w.view.layer = layer
    assert updates == [True]
    assert w.view.layer is layer
    widget.paintEvent(None)
    fills = [c for c in PAINTERS[-1].calls if c[0] == "fill"]
    assert fills and errors == []
    # Ascender..descender fill the 100 px height; the advance is centred. The
    # closed path starts at its last node (500, 700).
    span = layer.ascender - layer.descender
    scale = 100 / span
    expected = (
        (200 - 500 * scale) / 2 + 500 * scale,
        100 - (700 - layer.descender) * scale,
    )
    _, ops, _, device = fills[-1][:4]
    first = ops[0]
    assert first[0] == "M"
    assert gc.apply(device, first[1], first[2]) == pytest.approx(expected)
    w.close()
