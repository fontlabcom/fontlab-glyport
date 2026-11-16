# this_file: tests/test_parameter_numbers.py
"""Typed bool schema conversion; Foundation tests own their locale objects."""

import sys

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.parameter_numbers import normalize


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        True,
        0,
        1,
        -1,
        0.5,
        -0.5,
        1e-46,
        1e-300,
        float("nan"),
        float("inf"),
        -float("inf"),
    ],
)
def test_normalize_when_number_or_nil_then_retains_numeric_semantics(value):
    actual = normalize(value)
    if value is None:
        assert actual is False, (
            "Nil typed bool must normalize through nil.boolValue to false"
        )
    else:
        assert actual is value, (
            "Existing NSNumber-like values must not be converted to float32"
        )


@pytest.mark.parametrize("value", [[], {}, object()])
def test_normalize_when_unqualified_object_then_explicit_unsupported(value):
    with pytest.raises(UnsupportedCapability, match="parameter"):
        normalize(value)


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Requires owned macOS Foundation objects"
)
@pytest.mark.parametrize("locale_name", ["en_US", "de_DE", "pl_PL"])
@pytest.mark.parametrize(
    "text, expected",
    [
        ("", 0),
        ("YES", 0),
        ("true", 0),
        ("1", 1),
        ("-1", -1),
        ("1e-3", 1),
        ("  -2x", -2),
        ("١", 1),
        ("１", 1),
        ("9223372036854775808", 2**63 - 1),
        ("-9223372036854775809", -(2**63)),
    ],
)
def test_normalize_when_integer_branch_then_uses_nsstring_integer_value(
    locale_name, text, expected
):
    assert normalize(text, locale_name=locale_name) == expected


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Requires owned macOS Foundation objects"
)
@pytest.mark.parametrize(
    "locale_name, decimal", [("en_US", "."), ("de_DE", ","), ("pl_PL", ",")]
)
def test_normalize_when_decimal_branch_then_preserves_rounding_and_nil_sentinel(
    locale_name, decimal
):
    def convert(text):
        return normalize(text.replace(".", decimal), locale_name=locale_name)

    assert convert("0.5") == 0.5
    assert convert("-0.5") == -0.5
    assert convert("0.0junk") == float(2**63), (
        "Upstream helper's failed-parse sentinel is nonzero"
    )
    assert convert("1.0e-46") == 0.0, "String decimal parsing rounds through float32"
    assert convert("1.0e-45") > 0.0
    assert normalize(1e-46) != 0.0, "Existing numeric doubles are retained"


def test_normalize_when_platform_lacks_foundation_then_string_refuses(monkeypatch):
    import fontlab_glyport.model.parameter_numbers as numbers

    monkeypatch.setattr(numbers.sys, "platform", "win32")
    with pytest.raises(UnsupportedCapability, match="Foundation"):
        normalize("1")


def test_normalize_when_foundation_operation_raises_then_drains_owned_pool(monkeypatch):
    import fontlab_glyport.model.parameter_numbers as numbers

    calls = []

    class FailedString:
        def klass(self, name):
            return name

        def send(self, receiver, selector, *args, **kwargs):
            calls.append(selector)
            return 123

        def string(self, text):
            raise RuntimeError("owned string conversion failed")

    monkeypatch.setattr(numbers.sys, "platform", "darwin")
    monkeypatch.setattr(numbers, "_foundation", lambda: FailedString())
    with pytest.raises(RuntimeError, match="owned string"):
        normalize("1")
    assert calls == ["new", "drain"], (
        "Every exception after pool acquisition must drain it"
    )


@pytest.mark.parametrize(
    "error", [OSError("missing framework"), AttributeError("missing runtime symbol")]
)
def test_foundation_when_runtime_unavailable_then_typed_capability_error(
    monkeypatch, error
):
    import fontlab_glyport.model.parameter_numbers as numbers

    def unavailable():
        raise error

    monkeypatch.setattr(numbers, "_Foundation", unavailable)
    with pytest.raises(UnsupportedCapability, match="Foundation") as caught:
        numbers._foundation.__wrapped__()
    assert caught.value.capability == "GSCustomParameter.numeric.Foundation"


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Requires owned macOS Foundation objects"
)
def test_normalize_when_locale_type_is_invalid_then_refuses_before_bridge_call():
    with pytest.raises(TypeError, match="locale_name"):
        normalize("1", locale_name=123)


def test_import_when_framework_loading_is_forbidden_then_stays_cold():
    import subprocess

    code = """
import ctypes
from importlib import import_module
def forbid(*args, **kwargs):
    raise AssertionError('Eager Foundation load')
ctypes.CDLL = forbid
numbers = import_module('fontlab_glyport.model.parameter_numbers')
assert numbers.normalize(0.5) == 0.5
"""
    process = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=10,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr


@pytest.mark.skipif(
    sys.platform != "darwin", reason="Requires owned macOS Foundation objects"
)
def test_normalize_when_default_decimal_formatter_is_reused_then_keeps_process_cache():
    import ctypes

    import fontlab_glyport.model.parameter_numbers as numbers

    runtime = numbers._foundation()
    pool = runtime.send(runtime.klass("NSAutoreleasePool"), "new")
    try:
        separator = runtime.send(runtime.locale(None), "decimalSeparator")
        decimal = runtime.send(separator, "UTF8String", result=ctypes.c_char_p).decode()
    finally:
        runtime.send(pool, "drain", result=None)
    normalize("0" + decimal + "0")
    first = runtime.default_formatter
    assert first is not None, "Default decimal path must acquire its process formatter"
    normalize("1" + decimal + "0")
    assert runtime.default_formatter == first
