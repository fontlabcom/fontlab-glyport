# this_file: tests/test_issue201_final_review.py
"""Issue 201 final-review fixes: a failing sink in native painters (M4) and one
GSDocument per font for document events (M5). H1/M1: test_custom_parameter_order."""

from types import SimpleNamespace

import pytest
from test_drawing_editor import Info, Recorder
from test_glyphsapp_session import _session
from test_issue201_native_hooks import _native, make_plugins

from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.model import GSCustomParameter, Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER
from fontlab_glyport.plugins.loader import load_plugin
from fontlab_glyport.plugins.tool_bridge import ToolBridge


@pytest.fixture
def plugins():
    return make_plugins()


def test_native_paint_when_sink_raises_then_both_printed_never_raised(capsys):
    painters, canvas, _, _ = _native([Info(0, True)])

    def bad_sink(error, owner):
        raise OSError("output closed")

    def broken(context):
        raise ValueError("plugin broke")

    painters.sink = bad_sink
    painters.register(AFTER_NATIVE_LAYER, broken)
    canvas.paint(1, Recorder())  # the plugin error path
    canvas.block = None  # textBlocks() fails: the outer error path
    canvas.paint(1, Recorder())
    err = capsys.readouterr().err
    assert (
        err.count("OSError: output closed") == 2 and "ValueError: plugin broke" in err
    )


class _Backend(FakeBackend):
    def __init__(self, packages=()):
        super().__init__()

    def font_id_for(self, package):
        return "font" if package == "pkg" else None


def test_session_document_when_event_package_then_font_parent(tmp_path):
    ctx, session = _session(tmp_path)
    session.backend = _Backend()
    session.model = Model(session.backend)
    document = session._document("pkg")
    assert document is session.model.font.parent, "the currentDocument object"
    assert session._document("pkg") is document and session._document("x") is None
    ctx.close()


def test_provider_document_when_event_package_then_font_parent(monkeypatch, tmp_path):
    from fontlab_glyport.glyphsapp import fontlab_bridge as fb

    seen, real_model = {}, fb.Model

    class Stop(Exception):
        pass

    def bridge(**kwargs):
        seen.update(kwargs)
        raise Stop

    monkeypatch.setattr(fb, "FontLabBackend", _Backend)
    monkeypatch.setattr(fb, "Model", lambda b: seen.setdefault("model", real_model(b)))
    monkeypatch.setattr(fb, "FontLabGlyphsBridge", bridge)
    with pytest.raises(Stop):
        fb.fontlab_glyphsapp_provider(
            ExecutionContext(tmp_path, "glyphs3"), version=(3.2, 3234.0), packages=[]
        )
    document = seen["document"]
    assert document("pkg") is seen["model"].font.parent is document("pkg")
    assert document(SimpleNamespace()) is None


# --- LOW fixes ------------------------------------------------------------------
def test_tool_activate_when_repeated_then_painters_not_doubled(plugins):
    host, env, module, _ = plugins

    class Tool(module.SelectTool):
        def foreground(self, layer):
            pass

        def background(self, layer):
            pass

    handle = load_plugin(Tool, env)
    activate = host.entries("tool")[0][3]
    activate()
    activate()
    assert len(host.entries("painter")) == 2 and len(handle.painters) == 2


def test_bridge_deactivate_when_will_deactivate_fails_then_painters_removed(plugins):
    _, _, module, _ = plugins

    class Tool(module.SelectTool):
        def willDeactivate(self):
            raise ValueError("bad willDeactivate")

    painters, _, _, _ = _native([Info(0, True)])
    removed, sunk = [], []
    bridge = ToolBridge(
        None,
        Tool.alloc().init(),
        painters,
        deactivate=lambda: removed.append(True),
        sink=lambda e, o: sunk.append(str(e)),
    )
    assert bridge.deactivate() is None
    assert removed == [True] and sunk == ["bad willDeactivate"]


@pytest.mark.parametrize("name", [7, b"Filter", ["x"]])
def test_custom_parameter_name_when_not_str_then_type_error(name):
    with pytest.raises(TypeError, match="strings or None"):
        GSCustomParameter(name, 1)
    parameter = GSCustomParameter("ok", 1)
    with pytest.raises(TypeError):
        parameter.name = name
    assert parameter.name == "ok"
