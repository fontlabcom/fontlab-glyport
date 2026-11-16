# this_file: tests/test_adaptation_edges.py
"""Owned fixtures for adaptation boundaries; never execute corpus code."""

# ruff: noqa: S102 -- executing owned fixtures verifies semantics.
import json
from pathlib import Path

import pytest
from test_adaptation import adapt

from fontlab_glyport import AdaptationError, adapt_source


@pytest.mark.parametrize(
    "source",
    ["", "# comment\r\n", "value = xrange(3)\n", "print('hello')", "s = u'café'\n"],
)
def test_pass_through_edge_cases(tmp_path, source):
    result = adapt(tmp_path, source)
    assert not result.adaptations
    assert result.path.read_bytes() == source.encode()


def test_cache_changes_and_rebinding(tmp_path):
    result = adapt(tmp_path, "print 'x'\n")
    other = tmp_path / "other.py"
    other.write_bytes(result.original_path.read_bytes())
    reused = adapt_source(other, profile="glyphs2", cache_dir=tmp_path / "cache")
    assert reused.cache_hit and reused.path == result.path
    assert reused.compile().co_filename == str(other)
    assert reused.diagnostics[0].location.path == str(other)
    changed = adapt(tmp_path, "print 'y'\n")
    assert changed.path != result.path


def test_cache_integrity_failure(tmp_path):
    result = adapt(tmp_path, "print 1\n")
    result.path.write_text("bad data")
    with pytest.raises(AdaptationError, match="integrity"):
        adapt_source(
            result.original_path, profile="glyphs2", cache_dir=tmp_path / "cache"
        )


def test_encoded_source_and_docstring(tmp_path):
    original = tmp_path / "latin.py"
    raw = "# coding: latin-1\n'''café'''\nfrom __future__ import unicode_literals\nprint 5 / 2\n".encode(
        "latin-1"
    )
    original.write_bytes(raw)
    result = adapt_source(original, profile="glyphs2", cache_dir=tmp_path / "cache")
    scope = {}
    exec(result.compile(), scope)
    assert scope["__doc__"] == "café"
    assert original.read_bytes() == raw


def test_semicolon_prologue(tmp_path):
    result = adapt(tmp_path, "'''doc'''; value = 5 / 2\nprint value\n")
    scope = {}
    exec(result.compile(), scope)
    assert scope["value"] == 2 and scope["__doc__"] == "doc"


def test_traceback_and_unchanged_columns(tmp_path):
    result = adapt(tmp_path, "print 'café'\nvalue = 5 / 2\nraise ValueError('bad')\n")
    with pytest.raises(ValueError) as caught:
        exec(result.compile(), {})
    tb = caught.value.__traceback__
    while tb.tb_next:
        tb = tb.tb_next
    assert tb.tb_frame.f_code.co_filename == str(result.original_path)
    assert result.translate(tb.tb_lineno).line == 3
    assert result.translate(3, 7).column == 7
    spans = json.loads(Path(result.source_map.path).read_text())["spans"]
    assert len(spans) == len(result.path.read_text())


def test_reserved_helper_name(tmp_path):
    with pytest.raises(AdaptationError, match="reserved") as caught:
        adapt(tmp_path, "print 1\n_glyport_div = 3\nvalue = 5 / 2\n")
    assert caught.value.location.line == 2


def test_augmented_division_fails_explicitly(tmp_path):
    with pytest.raises(AdaptationError, match="augmented"):
        adapt(tmp_path, "print 1\nx = 5\nx /= 2\n")


def test_helper_errors_and_operand_evaluation(tmp_path):
    result = adapt(
        tmp_path,
        "print 1\nseen = []\ndef number(n):\n seen.append(n)\n return n\nvalue = number(5) / number(2)\n",
    )
    scope = {}
    exec(result.compile(), scope)
    assert scope["seen"] == [5, 2] and scope["value"] == 2
    from fontlab_glyport.runtime import _glyport_div

    with pytest.raises(ZeroDivisionError):
        _glyport_div(1, 0)
    with pytest.raises(TypeError):
        _glyport_div("x", 2)


@pytest.mark.parametrize("name", ["iterkeys", "itervalues", "iteritems"])
def test_dict_iteration_is_iterator(tmp_path, name):
    result = adapt(tmp_path, f"print 1\nd = {{'a': 1, 'b': 2}}\nvalues = d.{name}()\n")
    scope = {}
    exec(result.compile(), scope)
    assert iter(scope["values"]) is scope["values"]
    assert len(list(scope["values"])) == 2


def test_missing_source(tmp_path):
    with pytest.raises(AdaptationError) as caught:
        adapt_source(tmp_path / "missing.py", profile="auto", cache_dir=tmp_path)
    assert caught.value.location.path.endswith("missing.py")


def test_unknown_profile(tmp_path):
    with pytest.raises(AdaptationError, match="profile"):
        adapt(tmp_path, "print 1\n", profile="bogus")
