# this_file: tests/test_issue106_round15_cocoa.py
"""Predicate filtering without Cocoa/PyObjC or evaluation of source strings."""

import pytest
from ui_doubles_session import make_session

from fontlab_glyport.errors import UnsupportedCapability


def test_predicate_filters_array_with_object_and_key_placeholders(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        f = ctx.import_module("Foundation")
        rows = f.NSArray(
            [{"name": "one", "tags": ["mark"]}, {"name": "two", "tags": []}]
        )
        predicate = f.NSPredicate.predicateWithFormat_("name == %@", "one")
        assert rows.filteredArrayUsingPredicate_(predicate) == rows[:1]
        assert f.NSPredicate.predicateWithFormat_(
            "%K CONTAINS %@", "tags", "mark"
        ).evaluateWithObject_(rows[0])
        assert f.NSPredicate.predicateWithFormat_(
            'tags CONTAINS "mark"'
        ).evaluateWithObject_(rows[0])
        with pytest.raises(UnsupportedCapability):
            f.NSPredicate.predicateWithFormat_("FUNCTION(name, 'anything')")
    ctx.close()
