# this_file: tests/test_legacy_api.py
"""Owned controls for parseable legacy source, never reference/corpus execution."""
# ruff: noqa: S102 -- only owned fixture text is executed.

import builtins
from pathlib import Path

import pytest

from fontlab_glyport import adapt_source
from fontlab_glyport.execution import ExecutionContext


def execute(tmp_path, source, profile="glyphs2"):
    path = tmp_path / "owned.py"
    path.write_text(source)
    result = adapt_source(path, profile=profile, cache_dir=tmp_path / "cache")
    scope = {}
    exec(result.compile(), scope)
    assert path.read_text() == source
    return scope, result


@pytest.mark.parametrize(
    "method,expected",
    [
        ("iteritems", [("a", 1)]),
        ("iterkeys", ["a"]),
        ("itervalues", [1]),
        ("has_key", True),
    ],
)
def test_dictionary_legacy_method(tmp_path, method, expected):
    expression = f'd.{method}("a")' if method == "has_key" else f"list(d.{method}())"
    scope, result = execute(tmp_path, f'd={{"a":1}}\nvalue={expression}\n')
    assert scope["value"] == expected
    assert any(step.id == "py2.legacy_methods" for step in result.adaptations)


def test_custom_method_and_receiver_evaluated_once_with_arguments(tmp_path):
    source = """events=[]
class Custom:
    def has_key(self,*args,**kwargs):
        events.append((args,kwargs));return 'custom'
def receiver():
    events.append('receiver');return Custom()
value=receiver().has_key('a',flag=True)
"""
    scope, _ = execute(tmp_path, source)
    assert scope["value"] == "custom" and scope["events"] == [
        "receiver",
        (("a",), {"flag": True}),
    ]


def test_existing_dict_subclass_method_and_descriptor_error_are_preserved(tmp_path):
    source = """class Custom(dict):
    def has_key(self,key): return ('custom',key)
class Broken(dict):
    @property
    def iteritems(self): raise AttributeError('descriptor error')
value=Custom().has_key('a')
try: Broken().iteritems()
except AttributeError as error: message=str(error)
"""
    scope, _ = execute(tmp_path, source)
    assert scope["value"] == ("custom", "a") and scope["message"] == "descriptor error"


def test_fallback_does_not_call_overridden_modern_items(tmp_path):
    scope, _ = execute(
        tmp_path,
        """class Custom(dict):
    def items(self): raise AssertionError('wrong dispatch')
d=Custom(a=1)
values=d.iteritems()
value=list(values)
""",
    )
    assert scope["value"] == [("a", 1)] and iter(scope["values"]) is scope["values"]


@pytest.mark.parametrize(
    "expression",
    [
        '({"a":1}).has_key("a")',
        '({"a":1} # keep . comment\n).has_key("a")',
        'f"{dict(a=1).has_key(chr(97))}"',
    ],
)
def test_parentheses_comments_and_fstring_expressions(tmp_path, expression):
    scope, result = execute(tmp_path, "value=" + expression + "\n")
    assert scope["value"] in (True, "True")
    if "# keep" in expression:
        assert "# keep . comment" in result.path.read_text()


def test_nested_attribute_rewrites_and_unbound_dictionary_methods(tmp_path):
    scope, _ = execute(
        tmp_path,
        """d={'a':1}
value=dict.has_key(d,'a')
pairs=list(dict.iteritems(d))
class Custom:
    @property
    def has_key(self): return {'x':2}
keys=list(Custom().has_key.iterkeys())
""",
    )
    assert (
        scope["value"] is True
        and scope["pairs"] == [("a", 1)]
        and scope["keys"] == ["x"]
    )


@pytest.mark.parametrize("profile", ["glyphs3", "glyphs4", "auto"])
def test_modern_unknown_profiles_keep_original_bytes(tmp_path, profile):
    source = 'd={}\nvalue=d.has_key("a")\n'
    path = tmp_path / "owned.py"
    path.write_text(source)
    result = adapt_source(path, profile=profile, cache_dir=tmp_path / "cache")
    assert result.path.read_bytes() == path.read_bytes() and not result.adaptations


def test_declared_glyphs2_auto_profile_uses_legacy_path(tmp_path):
    scope, _ = execute(
        tmp_path, '# GLYPHS_VERSION: 2\nvalue={}.has_key("a")\n', profile="auto"
    )
    assert scope["value"] is False


def test_execution_scope_builtins_and_user_bindings_are_isolated(tmp_path):
    path = tmp_path / "owned.py"
    path.write_text("""value=[unichr(i) for i in xrange(65,67)]
checks=(isinstance('a',unicode),isinstance(b'a',basestring),long('7'))
xrange=lambda *args: ['custom']
custom=list(xrange(1))
""")
    context = ExecutionContext(tmp_path, "glyphs2", cache_dir=tmp_path / "cache")
    try:
        assert context.run(path).status == "passed"
        assert context.globals["value"] == ["A", "B"] and context.globals["checks"] == (
            True,
            True,
            7,
        )
        assert context.globals["custom"] == ["custom"]
    finally:
        context.close()
    assert not hasattr(builtins, "xrange") and not hasattr(builtins, "unichr")


def test_local_binding_error_and_imported_helper_builtins_keep_scope(tmp_path):
    (tmp_path / "helper.py").write_text("value=list(xrange(2))\n")
    path = tmp_path / "owned.py"
    path.write_text("""import helper
value=helper.value
def local():
    value=xrange(1)
    xrange='later'
try: local()
except UnboundLocalError: local_error=True
""")
    context = ExecutionContext(tmp_path, "glyphs2", cache_dir=tmp_path / "cache")
    try:
        assert context.run(path).status == "passed"
        assert context.globals["value"] == [0, 1] and context.globals["local_error"]
    finally:
        context.close()


@pytest.mark.parametrize(
    "binding",
    [
        "_glyport_legacy_attrs=1",
        "def f(_glyport_legacy_attrs): pass",
        "class _glyport_legacy_attrs: pass",
        "import os as _glyport_legacy_attrs",
        "def f():\n global _glyport_legacy_attrs",
    ],
)
def test_reserved_helper_bindings_are_diagnosed_before_cache_publication(
    tmp_path, binding
):
    from fontlab_glyport.errors import AdaptationError

    path = tmp_path / "owned.py"
    path.write_text(binding + '\nvalue={}.has_key("a")\n')
    with pytest.raises(AdaptationError, match="reserved helper name"):
        adapt_source(path, profile="glyphs2", cache_dir=tmp_path / "cache")


def test_docstring_future_unicode_crlf_and_map_provenance(tmp_path):
    import json

    from fontlab_glyport.receipt import SourceLocation

    source = '"""Café metadata."""\r\nfrom __future__ import annotations\r\n# keep attribution\r\nvalue={}.has_key("a")\r\n'
    path = tmp_path / "owned.py"
    path.write_bytes(source.encode())
    result = adapt_source(path, profile="glyphs2", cache_dir=tmp_path / "cache")
    scope = {}
    exec(result.compile(), scope)
    assert scope["__doc__"] == "Café metadata." and scope["value"] is False
    assert "# keep attribution" in result.path.read_text()
    assert path.read_bytes() == source.encode()
    stage = result.adaptations[0]
    assert (
        stage.source_map
        and json.loads(Path(stage.source_map.path).read_text())["spans"]
    )
    context = ExecutionContext(tmp_path, "glyphs2", cache_dir=tmp_path / "cache")
    try:
        context._compile(path)
        generated = result.path.read_text().splitlines()
        line = next(
            i + 1 for i, text in enumerate(generated) if text.startswith("value=")
        )
        mapped = context._translate(SourceLocation(str(path), line, 1))
        assert mapped.line == 4 and mapped.path == str(path)
    finally:
        context.close()


def test_live_iterator_argument_errors_and_missing_custom_attributes(tmp_path):
    source = """d={'a':1}
iterator=d.iteritems()
d['b']=2
try: next(iterator)
except RuntimeError: changed=True
try: d.has_key()
except TypeError: missing_argument=True
try: d.iteritems(1)
except TypeError: extra_argument=True
class Custom: pass
try: Custom().has_key('a')
except AttributeError: missing_method=True
"""
    scope, _ = execute(tmp_path, source)
    assert all(
        scope[key]
        for key in ("changed", "missing_argument", "extra_argument", "missing_method")
    )


def test_public_declared_auto_entrypoint_runs_owned_legacy_controls(tmp_path):
    from test_runtime_review_fixes import fixture_host

    from fontlab_glyport import run_script

    path = tmp_path / "owned.py"
    path.write_text(
        '# GLYPHS_VERSION: 2\nvalue=list({"a":1}.iteritems())\nletters=[unichr(i) for i in xrange(65,67)]\n'
    )
    handle = run_script(path, host=fixture_host())
    try:
        assert handle.context.profile == "glyphs2"
        assert handle.context.globals["value"] == [("a", 1)]
        assert handle.context.globals["letters"] == ["A", "B"]
    finally:
        handle.close()


def test_modern_execution_builtins_remain_python3(tmp_path):
    context = ExecutionContext(tmp_path, "glyphs3")
    try:
        assert not any(
            name in context.builtins
            for name in ("xrange", "unichr", "long", "basestring", "unicode")
        )
    finally:
        context.close()


def test_single_quoted_fstring_and_inline_future_preserve_syntax(tmp_path):
    scope, _ = execute(
        tmp_path,
        "from __future__ import annotations; value=f'{dict(a=1).has_key(chr(97))}'\n",
    )
    assert scope["value"] == "True"


def test_declared_latin1_and_nonascii_identifier_remain_exact(tmp_path):
    path = tmp_path / "owned.py"
    data = b'# coding: latin-1\n\xe9={"a":1}\nvalue=\xe9.has_key("a")\n'
    path.write_bytes(data)
    result = adapt_source(path, profile="glyphs2", cache_dir=tmp_path / "cache")
    scope = {}
    exec(result.compile(), scope)
    assert scope["value"] is True and path.read_bytes() == data


def test_missing_nonlegacy_attribute_never_receives_a_dictionary_fallback():
    from fontlab_glyport.runtime import _glyport_legacy_method

    with pytest.raises(AttributeError):
        _glyport_legacy_method({}, "not_a_legacy_method")


def test_reserved_binding_column_uses_unicode_characters(tmp_path):
    from fontlab_glyport.errors import AdaptationError

    path = tmp_path / "owned.py"
    source = 'é=1; _glyport_legacy_attrs=0\nvalue={}.has_key("a")\n'
    path.write_text(source)
    with pytest.raises(AdaptationError) as caught:
        adapt_source(path, profile="glyphs2", cache_dir=tmp_path / "cache")
    assert caught.value.location.line == 1 and caught.value.location.column == 6


def test_comment_between_dot_and_method_is_retained(tmp_path):
    source = 'value=({"a":1}. # retain this comment\n    has_key("a"))\n'
    scope, result = execute(tmp_path, source)
    assert scope["value"] is True and "# retain this comment" in result.path.read_text()


def test_existing_host_builtin_binding_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(
        builtins, "xrange", lambda *args: ["existing host binding"], raising=False
    )
    path = tmp_path / "owned.py"
    path.write_text("value=list(xrange(1))\n")
    context = ExecutionContext(tmp_path, "glyphs2", cache_dir=tmp_path / "cache")
    try:
        assert context.run(path).status == "passed"
        assert context.globals["value"] == ["existing host binding"]
    finally:
        context.close()
    assert builtins.xrange(1) == ["existing host binding"]
