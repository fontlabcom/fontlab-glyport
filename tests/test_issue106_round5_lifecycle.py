# this_file: tests/test_issue106_round5_lifecycle.py
"""Execution boundary regressions from the independent round-four review."""

import sys
from types import SimpleNamespace

import pytest
from ui_doubles_session import make_session

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext


@pytest.mark.parametrize("raises", [False, True])
@pytest.mark.parametrize("ends", [0, 1])
def test_c1_run_when_glyph_groups_unbalanced_then_published_and_diagnosed(
    tmp_path, raises, ends
):
    ctx, session = make_session(tmp_path)
    script = tmp_path / "undo.py"
    script.write_text(
        "from GlyphsApp import Glyphs\ng = Glyphs.font.glyphs['A']\n"
        "g.beginUndo()\ng.beginUndo()\ng.layers[0].width = 777\n"
        + "g.endUndo()\n" * ends
        + ("raise RuntimeError('script failed')\n" if raises else "")
    )
    try:
        if raises:
            with pytest.raises(RuntimeError, match="script failed"):
                ctx.run(script)
        else:
            ctx.run(script)
        font = session.model.font
        assert font._undo_depth == 0 and font.glyphs[0]._undo_count == 0
        assert session.backend.undo_events == [("begin", "Edit A"), ("end", None)]
        assert font.glyphs[0].layers[0].width == 777
        note = next(d for d in ctx.diagnostics if d.code == "UNBALANCED_UNDO_CLOSED")
        assert "A" in note.message
        # A stray old endUndo cannot close a later transaction.
        font.glyphs[0].endUndo()
        with font.undo_group("Next"):
            pass
        assert session.backend.undo_events[-2:] == [("begin", "Next"), ("end", None)]
    finally:
        ctx.close()


def test_c1_close_when_callback_leaves_group_open_then_published(tmp_path):
    ctx, session = make_session(tmp_path)
    glyph = session.model.font.glyphs[0]
    glyph.beginUndo()
    glyph.layers[0].width = 777
    ctx.close()
    assert session.backend.undo_events[-1] == ("end", None)
    assert glyph._undo_count == glyph._font._undo_depth == 0
    assert any(d.code == "UNBALANCED_UNDO_CLOSED" for d in ctx.diagnostics)


@pytest.mark.parametrize("font_group", [False, True])
def test_c1b_failed_close_when_begin_called_again_then_error_not_silent_nesting(
    tmp_path, monkeypatch, font_group
):
    ctx, session = make_session(tmp_path)
    glyph, backend = session.model.font.glyphs[0], session.backend
    original = backend.end_undo
    monkeypatch.setattr(
        backend,
        "end_undo",
        lambda: (_ for _ in ()).throw(RuntimeError("publish failed")),
    )
    with pytest.raises(RuntimeError, match="publish failed"):
        if font_group:
            with glyph._font.undo_group("Edit A"):
                glyph.layers[0].width = 600
        else:
            glyph.beginUndo()
            glyph.endUndo()
    assert glyph._font._undo_depth == 0
    assert glyph.__dict__.get("_undo_count", 0) == 0
    with pytest.raises(RuntimeError, match="[Uu]ndo|publish"):
        glyph.beginUndo()
    monkeypatch.setattr(backend, "end_undo", original)
    ctx.close()
    assert backend.undo_events[-1] == ("end", None)


@pytest.mark.parametrize("failure", [RuntimeError("publish failed"), SystemExit(7)])
def test_c1_failed_run_cleanup_when_script_succeeds_then_failure_is_loud(
    tmp_path, monkeypatch, failure
):
    ctx, session = make_session(tmp_path)
    end = session.backend.end_undo
    script = tmp_path / "undo.py"
    script.write_text(
        "from GlyphsApp import Glyphs\nGlyphs.font.glyphs[0].beginUndo()\n"
    )

    def fail():
        raise failure

    monkeypatch.setattr(session.backend, "end_undo", fail)
    try:
        with pytest.raises(type(failure)):
            ctx.run(script)
        assert ctx.last_stage.status == "failed"
        assert session.model.font._undo_depth == 0
        assert any(d.code == "UNDO_CLOSE_FAILED" for d in ctx.diagnostics)
    finally:
        monkeypatch.setattr(session.backend, "end_undo", end)
        ctx.close()


def test_c2_path_added_when_load_and_callback_exit_then_available_to_later_callback_only(
    tmp_path,
):
    root, shared, later = (tmp_path / name for name in ("plugin", "shared", "later"))
    for directory in (root, shared, later):
        directory.mkdir()
    (shared / "lazyhelper.py").write_text("from AppKit import NSColor\n")
    (later / "another.py").write_text("import sys\nvalue = 'later'\n")
    script = root / "plugin.py"
    script.write_text(
        f"import sys\nsys.path.insert(0, {str(shared)!r})\n"
        "def callback():\n    import lazyhelper\n    return lazyhelper.NSColor\n"
        f"def add_path():\n    sys.path.append({str(later)!r})\n"
        "def import_later():\n    import another\n    return another.value\n"
        "def sees_path():\n    return list(sys.path)\n"
    )
    ctx, _ = make_session(root)
    previous = list(sys.path)
    try:
        ctx.run(script)
        assert sys.path == previous
        color = ctx.wrap(ctx.globals["callback"])()
        with ctx:
            assert color is ctx.import_module("AppKit").NSColor
        assert str(shared) in ctx.wrap(ctx.globals["sees_path"])()
        ctx.wrap(ctx.globals["add_path"])()
        assert ctx.wrap(ctx.globals["import_later"])() == "later"
        scoped_paths = ctx.wrap(ctx.globals["sees_path"])()
        assert scoped_paths[0] == str(shared) and scoped_paths[-1] == str(later)
        assert sys.path == previous and "lazyhelper" not in sys.modules
        with ExecutionContext(root, "glyphs3") as other:
            with pytest.raises(ModuleNotFoundError):
                other.import_module("lazyhelper")
            assert str(shared) not in sys.path and str(later) not in sys.path
    finally:
        ctx.close()


@pytest.mark.parametrize(
    "failure",
    [
        StaleNativeObject("layer"),
        UnsupportedCapability("selection"),
        StopIteration(),
        RuntimeError("unexpected selection error"),
    ],
)
def test_i3_layer_when_selection_fails_then_only_reading_layer_raises(
    tmp_path, monkeypatch, failure
):
    ctx, session = make_session(tmp_path)
    ctx.implicit_imports = ("GlyphsApp",)
    calls = []

    def fail(_):
        calls.append(True)
        raise failure

    monkeypatch.setattr(session.backend, "current_layers", fail)
    script = tmp_path / "selection.py"
    script.write_text(
        "print('line one')\nassert Font is Glyphs.font\ndef later():\n    return Layer\n"
    )
    try:
        ctx.run(script)
        assert "line one" in "".join(ctx.output.strings) and calls == []
        with pytest.raises(type(failure)):
            ctx.wrap(ctx.globals["later"])()
        assert len(calls) == 1
    finally:
        ctx.close()


def test_c1_cleanup_when_script_and_publication_fail_then_original_error_has_cleanup_note(
    tmp_path, monkeypatch
):
    ctx, session = make_session(tmp_path)
    end = session.backend.end_undo

    def fail():
        raise RuntimeError("publish failed")

    script = tmp_path / "undo.py"
    script.write_text(
        "from GlyphsApp import Glyphs\nGlyphs.font.glyphs[0].beginUndo()\nraise ValueError('script failed')\n"
    )
    monkeypatch.setattr(session.backend, "end_undo", fail)
    try:
        with pytest.raises(ValueError, match="script failed") as error:
            ctx.run(script)
        assert any("publish failed" in note for note in error.value.__notes__)
        assert "publish failed" in "".join(ctx.output.strings)
        assert any(d.code == "UNDO_CLOSE_FAILED" for d in ctx.diagnostics)
        assert session.model.font._undo_depth == 0
    finally:
        monkeypatch.setattr(session.backend, "end_undo", end)
        ctx.close()


def test_c2_scope_exit_when_added_path_invalid_then_original_path_restored(tmp_path):
    original = list(sys.path)
    ctx = ExecutionContext(tmp_path, "glyphs3")
    try:
        with ctx:
            sys.path.append("invalid\0path")
        assert sys.path == original and not ctx._active
        with ctx:
            assert sys.path[-1] == "invalid\0path"
        assert sys.path == original
    finally:
        ctx.close()


def test_i3_layer_when_no_selection_then_actual_none_in_module_and_function(tmp_path):
    ctx, _ = make_session(tmp_path)
    ctx.implicit_imports = ("GlyphsApp",)
    script = tmp_path / "selection.py"
    script.write_text("assert Layer is None\ndef later():\n    return Layer\n")
    try:
        ctx.run(script)
        assert ctx.wrap(ctx.globals["later"])() is None
    finally:
        ctx.close()


def test_m1_filter_cleanup_when_env_lookup_fails_then_all_teardown_attempted(tmp_path):
    ctx, session = make_session(tmp_path)
    calls = []

    class BadPlugin:
        @property
        def _env(self):
            raise RuntimeError("bad filter env")

    session._filters = {1: BadPlugin(), 2: object()}
    session._env = object()
    close = lambda name: lambda: calls.append(name)
    session._menu = SimpleNamespace(
        built=True, target=SimpleNamespace(close=close("menu"))
    )
    session._plugin_host = SimpleNamespace(close=close("host"))
    session._painters = SimpleNamespace(close=close("painters"))
    session._appkit = {"close": close("AppKit")}
    session.bridge.close = close("bridge")
    with pytest.raises(RuntimeError, match="bad filter env"):
        session.close()
    assert calls == ["menu", "host", "painters", "AppKit", "bridge"]
    session._filters = {}
    ctx.close()
