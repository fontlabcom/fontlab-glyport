# this_file: tests/test_ui_nib_stack.py
"""NSStackView from XIB/NIB (R031 corpus). Fixture: self-authored ``Stack.xib``
and its ibtool NIB. Loaded stacks keep Interface Builder's frames; the stack
lays its arranged views out again only when they change."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Stack.xib", FIXTURES / "Stack.nib"
OUTLETS = ("dialog", "column", "row", "titleLabel", "optionBox", "okButton")


def _load(source):
    objc = make_objc_module({})
    owner_class = type(
        "StackOwner", (NSObject,), {name: objc.IBOutlet() for name in OUTLETS}
    )
    kit = make_appkit_classes(make_qt(), error_sink=print)
    owner = owner_class.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def _frame(view):
    (x, y), (w, h) = view.frame()
    return (x, y, w, h)


def test_stack_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))


def test_stack_when_parsed_then_layout_properties_and_arranged_children():
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    stacks = [n for n in nodes if n["source_class"] == "NSStackView"]
    column = next(n for n in stacks if n["properties"]["orientation"] == 1)
    assert column["properties"]["alignment"] == 5, "leading"
    assert column["properties"]["spacing"] == 8.0
    assert column["properties"]["edgeInsets"] == [10.0, 10.0, 10.0, 10.0]
    assert column["properties"]["distribution"] == 0, "fill"
    children = [n for n in nodes if n.get("parent_id") == column["node_id"]]
    assert len(children) == 3 and all(n["properties"]["arranged"] for n in children)


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_stack_then_arranged_views_keep_ib_frames(source):
    kit, owner, instance = _load(source)
    assert all(getattr(owner, name) is not None for name in OUTLETS)
    column, row = owner.column, owner.row
    assert isinstance(column, kit["NSStackView"]) and column.orientation() == 1
    assert column.arrangedSubviews() == [owner.titleLabel, owner.optionBox, row]
    assert row.arrangedSubviews()[1] is owner.okButton and row.spacing() == 6.0
    assert tuple(column.edgeInsets()) == (10.0, 10.0, 10.0, 10.0)
    assert _frame(owner.titleLabel) == (8, 114, 60, 16), "Interface Builder's frame"
    assert instance.diagnostics == []
    kit["close"]()


def test_stack_when_arranged_view_hidden_then_vertical_stack_closes_the_gap():
    kit, owner, _instance = _load(NIB)
    owner.optionBox.setHidden_(True)
    assert _frame(owner.titleLabel) == (10, 114, 60, 16), "top inset, leading inset"
    assert _frame(owner.row) == (10, 74, 160, 32), "label, spacing 8, then the row"
    owner.optionBox.setHidden_(False)
    assert _frame(owner.optionBox) == (10, 88, 100, 18)
    assert _frame(owner.row) == (10, 48, 160, 32)
    kit["close"]()


def test_stack_when_views_added_and_removed_then_horizontal_layout_follows():
    kit, owner, _instance = _load(XIB)
    row = owner.row
    extra = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 40, 20))
    row.addArrangedSubview_(extra)
    assert row.arrangedSubviews()[-1] is extra and extra.superview() is row
    assert [_frame(v)[0] for v in row.arrangedSubviews()] == [0, 88, 176]
    assert _frame(extra)[1] == 12, "top alignment in a 32-point row"
    row.removeArrangedSubview_(owner.okButton)
    assert owner.okButton not in row.arrangedSubviews()
    assert owner.okButton.superview() is row, "still a subview, as in AppKit"
    assert _frame(extra)[0] == 88
    row.insertArrangedSubview_atIndex_(owner.okButton, 0)
    assert row.arrangedSubviews()[0] is owner.okButton
    extra.removeFromSuperview()
    assert extra not in row.arrangedSubviews()
    kit["close"]()


def test_stack_when_built_in_code_then_orientation_spacing_and_insets_apply():
    kit = make_appkit_classes(make_qt(), error_sink=print)
    stack = kit["NSStackView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 100))
    stack.setOrientation_(1)
    stack.setSpacing_(4)
    stack.setEdgeInsets_((5, 6, 5, 6))
    views = [
        kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 30, 10)) for _ in range(2)
    ]
    for view in views:
        stack.addArrangedSubview_(view)
    assert [_frame(v) for v in views] == [(35, 85, 30, 10), (35, 71, 30, 10)], (
        "centred on X by default, top-down from the top inset"
    )
    stack.setAlignment_(6)  # trailing
    assert _frame(views[0])[0] == 64
    kit["close"]()
