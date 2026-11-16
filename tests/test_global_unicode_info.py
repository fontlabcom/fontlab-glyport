# this_file: tests/test_global_unicode_info.py
"""Global Unicode dispatch and synthesis follow the audited wrapper/manager."""

import inspect
from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSGlyphInfo, make_glyphsapp_module
from fontlab_glyport.glyphsapp.application_profiles import application_class


class Unreadable:
    def __getattribute__(self, name):
        raise AssertionError("Global lookup must not touch the active font")


@pytest.fixture
def app():
    return make_glyphsapp_module(
        NS(font=Unreadable()),
        object(),
        profile="glyphs3",
        defaults={},
        error_sink=lambda *args: None,
    ).Glyphs


@pytest.mark.parametrize(
    "value,name,code,script,case",
    [
        (65, "A", "0041", "latin", 1),
        ("0041", "A", "0041", "latin", 1),
        ("004a", "J", "004A", "latin", 1),
        ("0627", "alef-ar", "0627", "arabic", 0),
        ("00ﬀ", "ydieresis", "00FF", "latin", 2),
        ("FE8D", "alef-ar.isol", None, "arabic", 0),
        ("0378", "uni0378", "0378", None, 0),
        ("041", "uni041", "041", None, 0),
        ("000041", "uni000041", "000041", None, 0),
        ("000ﬀ", "uni000FF", "000FF", None, 0),
        ("00000000", "uni00000000", None, None, 0),
        ("80000000", "uni80000000", None, None, 0),
        ("FFFFFFFF", "uniFFFFFFFF", None, None, 0),
        ("100000000", "uni100000000", None, None, 0),
        ("FFFFFFFFF", "uniFFFFFFFFF", None, None, 0),
        (-1, "uni-001", "-001", None, 0),
        ("--41", "uni--41", "--41", None, 0),
        (" 4 1 ", "uni 4 1 ", " 4 1 ", None, 0),
        ("   ", "uni   ", "   ", None, 0),
        ("D800", "uniD800", "D800", None, 0),
        ("10FFFE", "u10FFFE", "10FFFE", None, 0),
    ],
)
def test_unicode_when_lookup_or_synthesis_then_preserves_source_contract(
    app, value, name, code, script, case
):
    info = app.glyphInfoForUnicode(value)
    assert isinstance(info, GSGlyphInfo)
    assert (info.name, info.unicode, info.script, info.case) == (
        name,
        code,
        script,
        case,
    )
    assert info.unicodeLegacy == ("FE8D" if value == "FE8D" else None), (
        "Legacy lookup preserves its separate field without primary promotion"
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "0",
        "00",
        "0ﬀ",
        "U+0041",
        "0x41",
        "nothex",
        "7FFFFFFF",
        "110000",
        "10FFFF",
        "00110000",
        "00\0",
        "😀0",
    ],
)
def test_unicode_when_no_information_then_returns_none(app, value):
    assert app.glyphInfoForUnicode(value) is None


@pytest.mark.parametrize("value", ["\ud800", "\ud8000", "\ud83d\ude000"])
def test_unicode_when_short_or_valid_pair_then_does_not_reject_as_malformed(app, value):
    assert app.glyphInfoForUnicode(value) is None


@pytest.mark.parametrize("value", [0xE000, 0xF0000, 0xFFFFD, 0x100000, 0x10FFFD])
def test_unicode_when_private_use_then_retains_private_category(app, value):
    info = app.glyphInfoForUnicode(value)
    assert info.category == "Private Use" and info.script is None


def test_unicode_when_direct_record_has_components_then_returns_independent_snapshots(
    app,
    monkeypatch,
    owned_info_manager,
):
    from fontlab_glyport.glyphsapp import GSGlyphsInfo

    selected = owned_info_manager(
        [
            {"name": "A", "unicode": "0041", "category": "Letter"},
            {
                "name": "acutecomb",
                "unicode": "0301",
                "category": "Mark",
                "subCategory": "Nonspacing",
            },
            {
                "name": "Aacute",
                "unicode": "00C1",
                "category": "Letter",
                "decompose": "A, acutecomb",
            },
        ]
    )
    selected.updateComponentsInfos()
    monkeypatch.setattr(GSGlyphsInfo, "_shared", selected)
    info = app.glyphInfoForUnicode("00C1")
    assert info.name == "Aacute"
    assert [item.name for item in info.components] == ["A", "acutecomb"]
    assert all(isinstance(item, GSGlyphInfo) for item in info.components)
    info.components.clear()
    assert [item.name for item in info.components] == ["A", "acutecomb"]


class IntSubclass(int):
    def __int__(self):
        raise AssertionError("Do not coerce an integer subclass")

    def __format__(self, spec):
        raise AssertionError("Use the wrapper's percent formatting")


@pytest.mark.parametrize("value", [65, IntSubclass(65), True, False])
def test_name_when_integer_then_dispatches_before_ignoring_explicit_font(app, value):
    expected = app.glyphInfoForUnicode(value)
    actual = app.glyphInfoForName(value, font=Unreadable())
    assert (actual.name, actual.unicode) == (expected.name, expected.unicode)


def test_name_when_integer_then_preserves_instance_method_override():
    calls = []

    class Application(application_class("glyphs3")):
        def glyphInfoForUnicode(self, *args, **kwargs):
            calls.append((args, kwargs))
            return "owned override"

    app = Application(NS(font=Unreadable()), object(), {}, None, lambda *args: None)
    assert app.glyphInfoForName(65, font=Unreadable()) == "owned override"
    assert calls == [((65,), {})]


@pytest.mark.parametrize("value", [None, [], 65, True, "", "0041"])
def test_unicode_when_explicit_font_then_selected_manager_receives_input(app, value):
    calls, result = [], object()

    class Manager:
        def glyphInfoForUnicode_(self, forwarded):
            calls.append(forwarded)
            return result

    class Font:
        def glyphsInfo(self):
            return Manager()

    assert app.glyphInfoForUnicode(value, font=Font()) is result, (
        "Mapped local lookup must return the selected manager's exact result"
    )
    if value is True:
        assert calls == ["0001"]
    elif type(value) is int:
        assert calls == ["0041"]
    else:
        assert len(calls) == 1 and calls[0] is value, (
            "Wrapper forwards bridge inputs; the manager owns qualification"
        )


class NoCoercion:
    def __str__(self):
        raise AssertionError("Do not coerce bridge input to text")

    def __index__(self):
        raise AssertionError("Do not coerce bridge input to integer")


class StringSubclass(str):
    pass


@pytest.mark.parametrize(
    "value",
    [
        65.0,
        b"0041",
        bytearray(b"0041"),
        [],
        {},
        pytest.param(NoCoercion(), id="unqualified-owned-object"),
        StringSubclass("0041"),
    ],
)
def test_unicode_when_bridge_type_is_unqualified_then_does_not_coerce(app, value):
    with pytest.raises(UnsupportedCapability) as error:
        app.glyphInfoForUnicode(value)
    assert error.value.capability == "Glyphs.glyphInfoForUnicode.inputType"


def test_unicode_when_signature_bound_then_uses_executable_wrapper_keyword(app):
    assert tuple(inspect.signature(app.glyphInfoForUnicode).parameters) == (
        "String",
        "font",
    )
    assert app.glyphInfoForUnicode(String="0041", font=None).name == "A"
    with pytest.raises(TypeError):
        app.glyphInfoForUnicode(Unicode="0041")


@pytest.mark.parametrize("value", ["\ud80000", "00\ud800", "\udc0000"])  # noqa: PT014 - distinct malformed UTF-16 surrogate inputs must all remain covered
def test_unicode_when_utf16_is_malformed_then_refuses_unsafe_native_path(app, value):
    with pytest.raises(UnsupportedCapability) as error:
        app.glyphInfoForUnicode(value)
    assert error.value.capability == "Glyphs.glyphInfoForUnicode.UTF16"


@pytest.mark.parametrize(
    "value,han",
    [
        (0x2E7F, False),
        (0x2E80, True),
        (0x2E99, True),
        (0x2E9A, False),
        (0x2E9B, True),
        (0x2EF3, True),
        (0x2EF4, False),
        (0x2EFF, False),
        (0x2F00, True),
        (0x2FD5, True),
        (0x2FD6, False),
        (0x3004, False),
        (0x3005, True),
        (0x3006, False),
        (0x3007, True),
        (0x3008, False),
        (0x3020, False),
        (0x3021, True),
        (0x3029, True),
        (0x302A, False),
        (0x3037, False),
        (0x3038, True),
        (0x303A, True),
        (0x303B, True),
        (0x303C, False),
        (0x33FF, False),
        (0x3400, True),
        (0x4DB5, True),
        (0x4DB6, False),
        (0x4DFF, False),
        (0x4E00, True),
        (0x9FCC, True),
        (0x9FCD, False),
        (0xF8FF, False),
        (0xF900, True),
        (0xFA6D, True),
        (0xFA6E, False),
        (0xFA6F, False),
        (0xFA70, True),
        (0xFAD9, True),
        (0xFADA, False),
        (0x2F7FF, False),
        (0x2F800, True),
        (0x2FA1D, True),
        (0x2FA1E, False),
        (0x1FFFF, False),
        (0x20000, True),
        (0x2A6D6, True),
        (0x2A6D7, False),
        (0x2A6FF, False),
        (0x2A700, True),
        (0x2B734, True),
        (0x2B735, False),
        (0x2B73F, False),
        (0x2B740, True),
        (0x2B81D, True),
        (0x2B81E, False),
        (0x2B81F, False),
        (0x2B820, True),
        (0x2CEA1, True),
        (0x2CEA2, False),
        (0x2CEAF, False),
        (0x2CEB0, True),
        (0x2EBE0, True),
        (0x2EBE1, False),
        (0x2FFFF, False),
        (0x30000, True),
        (0x3134A, True),
        (0x3134B, False),
        (0x1F1FF, False),
        (0x1F200, True),
        (0x1F2FF, True),
        (0x1F300, False),
    ],
)
def test_unicode_when_han_synthesis_boundary_then_uses_audited_historical_ranges(
    app, value, han
):
    # Seven-digit raw spellings bypass the maintained four-to-six-digit index.
    code = f"{value:07X}"
    info = app.glyphInfoForUnicode(code)
    assert info.script == ("han" if han else None)
    if value != 0xF8FF:
        assert info.category == ("Letter" if han else "Other")
    else:
        assert info.category == "Private Use"
    assert info.unicode == code, "Synthesis preserves the noncanonical spelling"
