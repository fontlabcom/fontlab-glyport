# this_file: tests/test_adaptation.py
"""Only owned miniature scripts are compiled or executed."""

# ruff: noqa: S102 -- executing owned fixtures is the semantic acceptance test.
import hashlib
import json
from pathlib import Path

import pytest

from fontlab_glyport import AdaptationError, adapt_source


def adapt(tmp_path, source, profile="glyphs2"):
    path = tmp_path / "original.py"
    path.write_bytes(source.encode())
    result = adapt_source(path, profile=profile, cache_dir=tmp_path / "cache")
    assert path.read_bytes() == source.encode(), "original bytes changed"
    return result


@pytest.mark.parametrize(
    "source,identifier",
    [
        ("print 1\n", "print_statement"),
        ("try:\n pass\nexcept ValueError, e:\n pass\n", "except_comma"),
        ("print 5 / 2\n", "integer_division"),
        ('print u"x"\n', "unicode_literals"),
        ("print {}.iteritems()\n", "dict_iter"),
        ("exec 'x = 1'\n", "exec_statement"),
        ("print `1`\n", "backticks"),
        ("print 1 <> 2\n", "ne_diamond"),
        ("raise ValueError, 'x'\n", "raise_tuple"),
        ("print 0755\n", "octal_literal"),
        ("print 1L\n", "long_literal"),
        ("print list(xrange(3))\n", "xrange"),
        ("print unicode(1)\n", "unicode_builtin"),
    ],
)
def test_transformation(tmp_path, source, identifier):
    result = adapt(tmp_path, source)
    assert "py2." + identifier in [a.id for a in result.adaptations]
    result.compile()
    previous = hashlib.sha256(source.encode()).hexdigest()
    for item in result.adaptations:
        assert item.input_sha256 == previous
        previous = item.output_sha256
        assert item.reason and item.source_map
        assert json.loads(Path(item.source_map.path).read_text())["spans"]
    assert previous == hashlib.sha256(result.path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("5 / 2", 2),
        ("-5 / 2", -3),
        ("5.0 / 2", 2.5),
        ("5 / 2.0", 2.5),
        ("True / 2", 0),
        ("9 / 2 / 2", 2),
        ("9 * 2 / 4", 4),
        ("9 / (2 / 2)", 9),
    ],
)
def test_division_semantics(tmp_path, expression, expected):
    result = adapt(tmp_path, "print 'marker'\nvalue = " + expression + "\n")
    scope = {}
    exec(result.compile(), scope)
    assert scope["value"] == expected


def test_future_division(tmp_path):
    result = adapt(
        tmp_path, "from __future__ import division\nprint 5 / 2\nvalue = 5 / 2\n"
    )
    scope = {}
    exec(result.compile(), scope)
    assert scope["value"] == 2.5
    assert "py2.integer_division" not in [a.id for a in result.adaptations]


def test_owned_semantic_fixture(tmp_path, capsys):
    result = adapt(
        tmp_path,
        """import io
out = io.StringIO()
print >>out, 'one',
print >>out, 'two'
exec 'value = 7' in globals()
d = {'a': 1, 'b': 2}
keys = d.keys()
d['c'] = 3
pairs = list(d.iteritems())
try:
 raise ValueError, 'bad'
except ValueError, error:
 message = '%s:%d' % (error, value)
print message
""",
    )
    scope = {}
    exec(result.compile(), scope)
    assert scope["out"].getvalue() == "one two\n"
    assert sorted(scope["keys"]) == ["a", "b"]
    assert sorted(scope["pairs"]) == [("a", 1), ("b", 2), ("c", 3)]
    assert capsys.readouterr().out == "bad:7\n"


def test_python3_passthrough(tmp_path):
    result = adapt(tmp_path, "# café\nvalue = 5 / 2\nprint(value)\n")
    assert result.adaptations == ()
    assert result.path.read_bytes() == result.original_path.read_bytes()


def test_cache_and_map(tmp_path, monkeypatch):
    result = adapt(tmp_path, "print 'café'\nvalue = 5 / 2\nraise ValueError('bad')\n")
    mtime = result.path.stat().st_mtime_ns
    again = adapt_source(
        result.original_path, profile="glyphs2", cache_dir=tmp_path / "cache"
    )
    assert again.cache_hit and again.path.stat().st_mtime_ns == mtime
    line = next(
        i
        for i, s in enumerate(result.path.read_text().splitlines(), 1)
        if "raise ValueError" in s
    )
    assert result.translate(line, 1).line == 3
    assert result.translate(line, 1).column == 1
    assert result.compile().co_filename == str(result.original_path)
    assert (
        adapt_source(
            result.original_path, profile="auto", cache_dir=tmp_path / "cache"
        ).path
        != result.path
    )
    import fontlab_glyport.adaptation as module

    monkeypatch.setattr(module, "PIPELINE_VERSION", "different")
    assert (
        adapt_source(
            result.original_path, profile="glyphs2", cache_dir=tmp_path / "cache"
        ).path
        != result.path
    )


def test_bad_source_has_original_location(tmp_path):
    with pytest.raises(AdaptationError) as caught:
        adapt(tmp_path, "print 1\nif :\n pass\n")
    assert caught.value.location.line == 2
    assert caught.value.location.column >= 1


def test_string_ambiguity(tmp_path):
    result = adapt(tmp_path, "print 'x'\nvalue = 'abc'\n")
    scope = {}
    exec(result.compile(), scope)
    assert isinstance(scope["value"], str)
    assert any(d.code == "PY2_STRING_AMBIGUITY" for d in result.diagnostics)


def _string_warnings(result):
    return [
        (d.location.line, d.location.column)
        for d in result.diagnostics
        if d.code == "PY2_STRING_AMBIGUITY"
    ]


def test_string_ambiguity_when_raw_unicode_then_python2_parser_locates_literals(
    tmp_path, monkeypatch
):
    """Python 3.14's stdlib tokenizer rejects ``ur''``; warnings come from the
    Python 2 parse tree, at each literal's first character, prefix included."""
    from fontlab_glyport import _adaptation_pipeline

    def stdlib_tokenizer_rejects(*args, **kwargs):
        raise _adaptation_pipeline.tokenize.TokenError(
            "'u' and 'r' prefixes are incompatible", (2, 7)
        )

    monkeypatch.setattr(
        _adaptation_pipeline.tokenize, "generate_tokens", stdlib_tokenizer_rejects
    )
    result = adapt(tmp_path, "a = 'x' 'y'\nraw = ur'\\u1234'\n")
    assert _string_warnings(result) == [(1, 5), (1, 9), (2, 7)]
    assert any(d.code == "PY2_RAW_UNICODE_REVIEW" for d in result.diagnostics)
