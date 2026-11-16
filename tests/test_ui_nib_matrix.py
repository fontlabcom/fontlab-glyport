# this_file: tests/test_ui_nib_matrix.py
"""NSMatrix from XIB/NIB (R031 corpus: radio groups bound to the defaults).
Fixture: self-authored ``Matrix.xib`` and its ibtool NIB."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import LOG, QCheckBox, make_qt
from ui_doubles_controls import QRadioButton

from fontlab_glyport.ui.cocoa import NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Matrix.xib", FIXTURES / "Matrix.nib"
KEY = "com.glyport.demo.direction"


def _load(source, defaults):
    objc = make_objc_module({})

    class MatrixOwner(NSObject):
        dialog = objc.IBOutlet()
        radios = objc.IBOutlet()
        checks = objc.IBOutlet()

        def init(self):
            self.calls = []
            return self

        @objc.IBAction
        def pickDirection_(self, sender):
            self.calls.append((sender.selectedCell().title(), sender.selectedRow()))

    kit = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    owner = MatrixOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_matrix_when_xib_and_nib_then_equal_graphs_with_row_major_cells():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    radios = next(n for n in nodes if n["source_id"] == "rad")["properties"]
    assert (radios["rows"], radios["columns"], radios["mode"]) == (2, 2, 0)
    assert radios["cellSize"] == [96.0, 18.0]
    assert radios["intercellSpacing"] == [8.0, 2.0]
    titles = [cell["title"] for cell in radios["cells"]]
    assert titles == ["North", "East", "South", "West"], "row-major"
    assert radios["cells"][0] == {
        "title": "North",
        "buttonType": 4,
        "state": 1,
        "tag": 1,
        "enabled": True,
    }
    assert not radios["cells"][3]["enabled"]
    checks = next(n for n in nodes if n["source_id"] == "chk")["properties"]
    assert checks["mode"] == 1 and checks["cells"][0]["buttonType"] == 3


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_radio_matrix_then_cells_selection_action_and_binding(source):
    defaults = {KEY: 2}
    kit, owner, instance = _load(source, defaults)
    radios = owner.radios
    assert isinstance(radios, kit["NSMatrix"])
    assert (radios.numberOfRows(), radios.numberOfColumns()) == (2, 2)
    assert radios.selectedCell().title() == "South", "the bound default selected"
    assert (radios.selectedRow(), radios.selectedColumn()) == (1, 0)
    buttons = [cell._qt for cell in radios.cells()]
    assert all(isinstance(b, QRadioButton) for b in buttons)
    assert buttons[2].isChecked() and not buttons[0].isChecked()
    rect = buttons[3].geometry
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (104, 20, 96, 18)
    assert not radios.cellAtRow_column_(1, 1).isEnabled()
    buttons[1].user_click()
    assert owner.calls == [("East", 0)] and defaults[KEY] == 1
    radios.selectCellWithTag_(1)
    assert radios.selectedCell().title() == "North" and owner.calls == [("East", 0)]
    assert instance.diagnostics == []
    kit["close"]()
    assert all(b.clicked.slots == [] for b in buttons), "close disconnects cells"


def test_matrix_when_checkbox_cells_then_independent_states():
    kit, owner, _instance = _load(NIB, {})
    checks = owner.checks
    bold, wide = checks.cells()
    assert isinstance(bold._qt, QCheckBox) and bold.state() == 1 and wide.state() == 0
    wide._qt.user_click()
    assert (bold.state(), wide.state()) == (1, 1)
    assert checks.selectedCell() is wide
    LOG.clear()
    kit["close"]()
