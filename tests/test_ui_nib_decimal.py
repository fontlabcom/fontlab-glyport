# this_file: tests/test_ui_nib_decimal.py
"""Number formatter limits archived as NSDecimalNumber (R031 corpus regression:
ibtool writes an unset minimum/maximum as NaN, ``NS.length`` 0 and negative)."""

import struct
from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import make_qt

from fontlab_glyport.ui.cocoa import NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_archive import Archived
from fontlab_glyport.ui.nib_graph import (
    _decimal,
    _nib_control,
    graph_from_nib,
    graph_from_xib,
)
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module


def _number(mantissa: int, exponent: int = 0, negative: bool = False, nan=False):
    words = []
    while mantissa:
        words.append(mantissa & 0xFFFF)
        mantissa >>= 16
    length = 0 if nan else len(words)
    return Archived(
        "NSDecimalNumberPlaceholder",
        {
            "NS.exponent": exponent,
            "NS.length": length,
            "NS.negative": negative or nan,
            "NS.compact": True,
            "NS.mantissa.bo": 1,
            "NS.mantissa": struct.pack("<8H", *(words + [0] * (8 - len(words)))),
        },
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (3, 3.0),
        (2.5, 2.5),
        ("7", 7.0),
        (_number(0, nan=True), None),
        (_number(0), 0.0),
        (_number(125, -1), 12.5),
        (_number(5, 2, negative=True), -500.0),
        (_number(70000), 70000.0),
    ],
)
def test_decimal_when_archived_value_then_float_or_none_for_nan(value, expected):
    assert _decimal(value) == expected, f"{value!r} decoded wrongly"


def test_nib_control_when_formatter_limits_are_decimal_numbers_then_decoded():
    formatter = Archived(
        "NSNumberFormatter", {"NS.min": 1, "NS.max": _number(0, nan=True)}
    )
    cell = Archived("NSTextFieldCell", {"NSContents": "1", "NSFormatter": formatter})
    props = _nib_control("NSTextField", Archived("NSTextField", {"NSCell": cell}))
    assert props["formatter"] == {"minimum": 1.0, "maximum": None}


FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Formatters.xib", FIXTURES / "Formatters.nib"


def test_formatters_when_xib_and_nib_then_equal_graphs_with_standalone_formatter():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    standalone = [n for n in nodes if n["source_class"] == "NSNumberFormatter"]
    assert len(standalone) == 1, "the top-level formatter is one node"
    assert standalone[0]["properties"] == {"minimum": -3.0}


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_formatters_then_limits_and_standalone_object(source):
    objc = make_objc_module({})

    class FormatOwner(NSObject):
        dialog = objc.IBOutlet()
        spare = objc.IBOutlet()
        limitCell = objc.IBOutlet()

    owner = FormatOwner.alloc().init()
    kit = make_appkit_classes(make_qt(), error_sink=print)
    instance = instantiate(load_graph(source), owner, kit)
    assert isinstance(owner.spare, kit["NSNumberFormatter"])
    assert (owner.spare.minimum(), owner.spare.maximum()) == (-3.0, None)
    assert owner.spare in instance.top_level, "the standalone formatter is retained"
    limited, free = sorted(
        owner.dialog.subviews(), key=lambda v: v.stringValue(), reverse=True
    )
    assert (limited.formatter().minimum(), limited.formatter().maximum()) == (2, 12.5)
    assert (free.formatter().minimum(), free.formatter().maximum()) == (None, None)
    assert owner.limitCell is limited, "an outlet to a cell gets its control"
