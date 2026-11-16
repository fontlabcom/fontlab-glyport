# this_file: tests/test_tab_activation_preservation.py
"""Empty Glyphs tabs use an owned native slot emitter, never copied UI state."""

import sys
from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.errors import NativeOperationError, UnsupportedCapability
from fontlab_glyport.model.fontlab_backend import FontLabBackend

SIGNAL, SLOT = "textChanged(QString)", "doCreateTextBlock(QString)"


class EmptyTabEmitter:
    """Native-shaped QObject connection: only changes after connect emit a slot."""

    def __init__(self, state):
        self.state, self.text, self.connection = state, "", None
        state.emitters.append(self)
        state.events.append("create")

    def setText(self, text):
        self.state.events.append(("text", text))
        if self.state.fail_at == "bootstrap" and text:
            raise self.state.failure
        previous, self.text = self.text, text
        if self.connection and text != previous:
            self.state.events.append(("emit", text))
            assert text == "", "Only literal empty text may reach FontLab's slot"
            # Measured FontLab behavior: even empty creation may activate the
            # old editor's rendered shape before the fresh block is selected.
            old_shape = getattr(self.state, "old_shape", None)
            if old_shape is not None:
                old_shape.active = True
            if self.state.fail_at == "emit":
                raise self.state.failure
            self.state.contents.append(text)
            self.state.selected = "new-empty-tab"
            if self.state.open_tab:
                self.state.open_tab(text)

    def connect(self, *connection):
        assert connection == (SIGNAL, self.state.main, SLOT)
        self.state.events.append("connect")
        if self.state.fail_at == "connect":
            raise self.state.failure
        if self.state.connected:
            self.connection = connection
        return self.state.connected

    def disconnect(self, *connection):
        assert connection == self.connection, "Disconnect the exact native slot triple"
        self.state.events.append("disconnect")
        self.connection = None
        if self.state.fail_at == "disconnect":
            raise self.state.failure
        return self.state.disconnected

    def deleteLater(self):
        self.state.events.append("delete")


@pytest.fixture
def host(monkeypatch):
    class Error(Exception):
        pass

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Empty tabs must not inspect copied raw text, cells, settings or unrelated glyphs"
        )

    package = NS(
        id=10, fgId=100, isValid=True, findName=forbidden, findUnicode=forbidden
    )
    state = NS(
        events=[],
        emitters=[],
        contents=[],
        selected="old-tab",
        main=object(),
        connected=True,
        disconnected=True,
        fail_at=None,
        failure=RuntimeError("native empty-tab failure"),
        open_tab=None,
    )
    workspace = NS(
        activeFontPanel=object(),
        getActiveTextBlock=lambda: None,
        getActiveCanvas=lambda: None,
    )
    module = NS(
        MainWindow=lambda: state.main, flWorkspace=NS(instance=lambda: workspace)
    )
    backend = FontLabBackend(packages=[package])
    monkeypatch.setattr(backend, "_native", lambda: module)

    def activate(font_id):
        state.events.append(("activate", font_id))
        workspace.currentPackage = package
        assert state.emitters[-1].connection is not None, "Connect before activating"
        if state.fail_at == "activate":
            old_shape = getattr(state, "old_shape", None)
            if old_shape is not None:
                old_shape.active = True
            raise state.failure

    tools = NS(Error=Error, set_active_font=activate, get_current_glyphs=forbidden)
    monkeypatch.setattr(backend, "_fontpr", lambda: tools)
    legacy_action = NS(objectName="actionOpen_Editor_Window", trigger=forbidden)
    legacy_window = NS(menuBar=None, findChildren=lambda cls: [legacy_action])
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(
            QLineEdit=lambda: EmptyTabEmitter(state),
            QAction=object,
            QApplication=NS(topLevelWidgets=lambda: [legacy_window]),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "PythonQt.QtCore",
        NS(QSettings=lambda: NS(value=lambda key, default: True)),
    )
    fid = backend._font_id(package)
    return NS(**locals())


@pytest.mark.parametrize(
    "context",
    [
        "font-window",
        "shaped-editor",
        "cross-font-empty-cells",
        "cross-font-mixed-cells",
    ],
)
def test_new_tab_starts_empty_without_copying_previous_context(host, context):
    source = NS(id=11, fgId=200, lib={"other-font": 7})
    old = NS(raw="A", rendered="B", shaping=True, shapes=[False, True], package=source)
    host.workspace.currentPackage = (
        source if context.startswith("cross-font") else host.package
    )
    host.workspace.activeFontPanel = None if context == "shaped-editor" else object()
    host.workspace.selected_cells = (
        ["X"] if context.endswith("empty-cells") else ["A", "X"]
    )
    before = (old.raw, old.rendered, list(old.shapes))
    host.backend.open_edit_view(host.fid)
    assert host.state.contents == [""] and host.state.selected == "new-empty-tab"
    assert host.workspace.currentPackage is host.package
    assert source.lib == {"other-font": 7}, "Other-font data must remain unchanged"
    assert (old.raw, old.rendered, old.shapes) == before, (
        "Keep the old editor unchanged"
    )
    events = host.state.events
    assert events[0] == "create" and events[1][0] == "text" and events[1][1]
    assert events[2:] == [
        "connect",
        ("activate", 100),
        ("text", ""),
        ("emit", ""),
        "disconnect",
        "delete",
    ]
    assert host.state.emitters[0].connection is None


def test_failed_connection_refuses_before_font_or_tab_mutation_and_deletes_emitter(
    host,
):
    host.state.connected = False
    with pytest.raises(UnsupportedCapability, match="empty|slot|connect"):
        host.backend.open_edit_view(host.fid)
    assert host.state.events[-2:] == ["connect", "delete"]
    assert host.state.contents == [] and host.state.selected == "old-tab"
    assert not any(
        isinstance(event, tuple) and event[0] == "activate"
        for event in host.state.events
    )


@pytest.mark.parametrize(
    "boundary", ["bootstrap", "connect", "activate", "emit", "disconnect"]
)
def test_native_boundary_failure_propagates_with_owned_emitter_cleanup(host, boundary):
    host.state.fail_at = boundary
    with pytest.raises(RuntimeError) as error:
        host.backend.open_edit_view(host.fid)
    assert error.value is host.state.failure
    assert host.state.events[-1] == "delete", "Every allocated emitter must be disposed"
    assert host.state.emitters[0].connection is None
    if boundary in ("activate", "emit", "disconnect"):
        assert host.state.events[-2] == "disconnect", "Disconnect before deleting"
    if boundary != "disconnect":
        assert host.state.contents == [] and host.state.selected == "old-tab"


def test_failed_disconnect_is_reported_and_still_deletes_owned_emitter(host):
    host.state.disconnected = False
    with pytest.raises(NativeOperationError, match="disconnect"):
        host.backend.open_edit_view(host.fid)
    assert host.state.events[-2:] == ["disconnect", "delete"]


def test_unregistered_font_refuses_before_main_window_or_emitter_access(
    host, monkeypatch
):
    host.backend._owned_fonts[host.package.id] = object()
    host.module.MainWindow = lambda: pytest.fail(
        "Do not touch GUI for unregistered font"
    )
    with pytest.raises(UnsupportedCapability, match="workspace-registered"):
        host.backend.open_edit_view(host.fid)
    assert host.state.events == []


def test_missing_main_window_refuses_without_allocating_emitter(host):
    host.state.main = None
    with pytest.raises(UnsupportedCapability, match="MainWindow|main window"):
        host.backend.open_edit_view(host.fid)
    assert host.state.events == []


def test_font_activation_tool_error_keeps_error_and_cleans_connection(host):
    def fail(font_id):
        raise host.Error("activation failed")

    host.tools.set_active_font = fail
    with pytest.raises(NativeOperationError, match="activation failed"):
        host.backend.open_edit_view(host.fid)
    assert host.state.contents == []
    assert host.state.events[-2:] == ["disconnect", "delete"]


@pytest.mark.parametrize("fails", [False, True])
def test_existing_text_guard_preserves_requested_glyphs_on_success_or_failure(
    host, monkeypatch, fails
):
    shape = NS(id=20, active=False)
    glyph = NS(layers=[NS(shapes=[shape])])
    host.package.findName = lambda name: glyph if name == "A" else None
    monkeypatch.setattr(host.backend, "_text_block", lambda fid: object())
    host.module.fgSymbol, host.module.fgSymbolList = lambda name: name, list

    def replace(symbols, mode):
        shape.active = True
        if fails:
            raise RuntimeError("text replacement failed")

    host.module.flItems = lambda: NS(requestContent=replace)
    if fails:
        with pytest.raises(RuntimeError, match="text replacement failed"):
            host.backend.set_edit_glyphs(host.fid, (("A",),))
    else:
        host.backend.set_edit_glyphs(host.fid, (("A",),))
    assert shape.active is False


@pytest.mark.parametrize("content", ["default", "text", "layers", "empty-layers"])
def test_public_new_tab_uses_empty_slot_then_applies_only_requested_content(
    monkeypatch, content
):
    from test_issue106_round9 import native as native_fixture

    native = native_fixture.__wrapped__(monkeypatch)
    native.package.master = "Regular"
    shape = native.layer.shapes[0]
    shape.active = False
    old_shape = NS(id=999, active=False)
    old_glyph = NS(name="B", layers=[NS(shapes=[old_shape])])
    old_source = NS(
        id=11, fgId=200, findName=lambda name: old_glyph if name == "B" else None
    )
    old = NS(
        names=["B"],
        shaping=True,
        package=old_source,
        getAllGlyphs=lambda: [NS(glyph=old_glyph)],
    )
    state = NS(
        events=[],
        emitters=[],
        contents=[],
        selected="old-tab",
        main=object(),
        connected=True,
        disconnected=True,
        fail_at=None,
        failure=RuntimeError("native"),
        open_tab=None,
        block=old,
        old_shape=old_shape,
    )
    workspace = NS(
        activeFontPanel=object(),
        getActiveTextBlock=lambda: None,
        getActiveCanvas=lambda: NS(textBlocks=lambda: [state.block]),
    )

    class Block:
        package, id = native.package, "new-block"

        def __init__(self):
            self.names = []

        def getAllGlyphs(self):
            return [
                NS(id=index, glyph=NS(name=name))
                for index, name in enumerate(self.names)
            ]

        def getLineIndex(self, info):
            return 0

        def symbolList(self):
            return NS(symbols=lambda: [NS(cr=False) for _ in self.names])

        def getActiveGlyph(self):
            return None

    def opened(text):
        assert text == "", "The native creation slot must receive literal empty text"
        state.block = Block()
        workspace.activeFontPanel = None

    def replace(symbols, mode):
        assert state.block is not old, "Content belongs only to the newly opened block"
        state.block.names = list(symbols)
        if symbols:
            shape.active = True  # Existing requestContent guard must restore it.

    class Error(Exception):
        pass

    state.open_tab = opened
    native.module.MainWindow = lambda: state.main
    native.module.flWorkspace.instance = lambda: workspace
    native.module.fgSymbol, native.module.fgSymbolList = lambda name: name, list
    native.module.flItems = lambda: NS(requestContent=replace)
    tools = NS(
        Error=Error,
        set_active_font=lambda font_id: state.events.append(("activate", font_id)),
    )
    monkeypatch.setattr(native.backend, "_fontpr", lambda: tools)
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QLineEdit=lambda: EmptyTabEmitter(state)),
    )
    if content == "default":
        tab = native.font.newTab()
    elif content == "text":
        tab = native.font.newTab("/A")
    elif content == "layers":
        tab = native.font.newTab([native.font.glyphs[0].layers[0]])
    else:
        tab = native.font.newTab([])
    expected = ["A"] if content in ("text", "layers") else []
    assert state.contents == [""] and state.block.names == expected
    assert [layer.parent.name for layer in tab.layers] == expected
    assert old.names == ["B"] and old.shaping is True and old_shape.active is False
    assert shape.active is False, "Requested text must retain saved activation flags"
    assert state.events[-2:] == ["disconnect", "delete"]


def old_rendered_block(host, *, name="A", cross_font=False, canvas=False):
    """A loaded old editor glyph; raw-symbol lookup would inspect another glyph."""
    shape = NS(id=500, active=False)
    glyph = NS(name=name, layers=[NS(shapes=[shape])])
    lookups = []
    source = NS(id=11, fgId=200) if cross_font else host.package

    def find(name_read):
        lookups.append(name_read)
        assert name_read == name, "Snapshot only actually rendered old glyphs"
        return glyph

    source.findName = find
    block = NS(
        package=source,
        raw="A",
        shaping=True,
        getAllGlyphs=lambda: [NS(glyph=glyph)],
        symbolList=lambda: pytest.fail(
            "Do not resolve copied raw symbols for an empty new tab"
        ),
    )
    host.workspace.getActiveTextBlock = lambda: None if canvas else block
    host.workspace.getActiveCanvas = lambda: (
        NS(textBlocks=lambda: [block]) if canvas else None
    )
    host.state.old_shape = shape
    return NS(**locals())


@pytest.mark.parametrize("boundary", ["success", "activate", "emit"])
def test_empty_tab_restores_old_rendered_activation_even_when_native_boundary_fails(
    host, boundary
):
    old = old_rendered_block(host)
    if boundary != "success":
        host.state.fail_at = boundary
        with pytest.raises(RuntimeError) as error:
            host.backend.open_edit_view(host.fid)
        assert error.value is host.state.failure
    else:
        host.backend.open_edit_view(host.fid)
        assert host.state.contents == [""]
    assert old.shape.active is False, (
        "Empty creation must restore old saved shape.active"
    )
    assert old.lookups == ["A"]
    assert host.state.events[-2:] == ["disconnect", "delete"]


@pytest.mark.parametrize("canvas", [False, True])
def test_old_shaped_editor_snapshots_rendered_B_and_not_raw_A(host, canvas):
    old = old_rendered_block(host, name="B", canvas=canvas)
    host.backend.open_edit_view(host.fid)
    assert old.shape.active is False and old.lookups == ["B"]
    assert old.block.raw == "A" and old.block.shaping is True
    assert host.state.contents == [""]


def test_old_cross_font_editor_preserves_source_package_not_target_guess(host):
    old = old_rendered_block(host, cross_font=True)
    host.backend.open_edit_view(host.fid)
    assert old.shape.active is False and old.lookups == ["A"]
    assert old.source is not host.package
    assert host.state.contents == [""] and host.workspace.currentPackage is host.package


@pytest.mark.parametrize("canvas", [False, True])
def test_empty_old_block_opens_empty_tab_without_glyph_lookups(host, canvas):
    block = NS(package=host.package, getAllGlyphs=lambda: None)
    host.workspace.getActiveTextBlock = lambda: None if canvas else block
    host.workspace.getActiveCanvas = lambda: NS(textBlocks=lambda: [block])
    host.backend.open_edit_view(host.fid)
    assert host.state.contents == [""]
    assert host.state.events[-2:] == ["disconnect", "delete"]


@pytest.mark.parametrize("boundary", ["block-info", "glyph-name", "shape-snapshot"])
def test_old_source_snapshot_failure_propagates_before_activation_or_emitter_allocation(
    host, boundary
):
    old = old_rendered_block(host)
    failure = RuntimeError("old source information failed")

    def fail(*args):
        raise failure

    if boundary == "block-info":
        old.block.getAllGlyphs = fail
    elif boundary == "glyph-name":

        class BrokenName:
            @property
            def name(self):
                raise failure

        old.block.getAllGlyphs = lambda: [NS(glyph=BrokenName())]
    else:
        old.source.findName = fail
    with pytest.raises(RuntimeError) as error:
        host.backend.open_edit_view(host.fid)
    assert error.value is failure
    assert old.shape.active is False and host.state.events == []


def test_all_loaded_rendered_glyphs_are_preserved_once_without_raw_or_font_scan(host):
    a, b, preactive = (
        NS(id=600, active=False),
        NS(id=601, active=False),
        NS(id=602, active=True),
    )
    glyphs = {
        "A": NS(name="A", layers=[NS(shapes=[a, preactive])]),
        "B": NS(name="B", layers=[NS(shapes=[b])]),
    }
    lookups = []

    def find(name):
        lookups.append(name)
        assert name in glyphs, "Only the rendered glyphs may be inspected"
        return glyphs[name]

    host.package.findName = find
    block = NS(
        package=host.package,
        getAllGlyphs=lambda: [NS(glyph=glyphs[name]) for name in ("A", "B", "A")],
    )
    host.workspace.getActiveTextBlock = lambda: block
    host.state.old_shape = a

    def opened(text):
        b.active, preactive.active = True, False

    host.state.open_tab = opened
    host.backend.open_edit_view(host.fid)
    assert [a.active, b.active, preactive.active] == [False, False, True]
    assert lookups == ["A", "B"], "Repeated rendered glyphs need only one snapshot"
