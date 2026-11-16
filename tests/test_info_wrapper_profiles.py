# this_file: tests/test_info_wrapper_profiles.py
"""Pinned public Glyphs 2/3/4 wrapper semantics using owned Python doubles."""

import inspect

import pytest

from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp import (
    GSApplication,
    glyphsapp_provider,
    make_glyphsapp_module,
)
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo

PROFILES = ("glyphs2", "glyphs3", "glyphs4")


class Manager:
    def __init__(self):
        self.calls = []
        self.result = object()

    def glyphInfoForName_(self, value):
        self.calls.append(("name", value))
        return self.result

    def glyphInfoForUnicode_(self, value):
        self.calls.append(("unicode", value))
        return self.result


class Font:
    def __init__(self, manager):
        self.manager = manager
        self.reads = 0

    def __bool__(self):
        raise AssertionError("The wrapper must compare font with None")

    def glyphsInfo(self):
        self.reads += 1
        return self.manager


class Forbidden:
    def __getattribute__(self, name):
        raise AssertionError("No implicit font, version or host reads")


class FormattedInt(int):
    def __format__(self, spec):
        assert spec == "04X", "Glyphs 4 uses the exact wrapper format specifier"
        return "OWNED_04X"


class RaisingInt(int):
    def __format__(self, spec):
        raise ValueError("owned-format-error")


@pytest.fixture
def managers(monkeypatch):
    shared, local = Manager(), Manager()
    monkeypatch.setattr(GSGlyphsInfo, "sharedManager", staticmethod(lambda: shared))
    return shared, local, Font(local)


def module_for(profile):
    return make_glyphsapp_module(
        Forbidden(), Forbidden(), profile=profile, defaults={}, error_sink=print
    )


@pytest.mark.parametrize("profile", PROFILES)
def test_signatures_when_version_selected_then_only_exact_keywords(profile, managers):
    app = module_for(profile).Glyphs
    expected = (
        ("String", "String")
        if profile == "glyphs2"
        else ("name", "String" if profile == "glyphs3" else "string_or_int")
    )
    for method, accepted, candidates in (
        (app.glyphInfoForName, expected[0], ("String", "name", "string_or_int")),
        (app.glyphInfoForUnicode, expected[1], ("String", "string_or_int", "Unicode")),
    ):
        assert str(inspect.signature(method)) == f"({accepted}, font=None)"
        assert method(**{accepted: "0041"}) is managers[0].result
        for rejected in set(candidates) - {accepted}:
            with pytest.raises(TypeError, match="unexpected keyword"):
                method(**{rejected: "0041"})
        with pytest.raises(TypeError):
            method()
        with pytest.raises(TypeError):
            method("A", None, None)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("lookup", ("glyphInfoForName", "glyphInfoForUnicode"))
@pytest.mark.parametrize(
    "value", (65, True, False, FormattedInt(65), "0041", None, object(), -1, 2**128)
)
def test_values_when_wrapped_then_source_dispatch_and_result_identity(
    profile, lookup, value, managers
):
    shared, local, font = managers
    app = module_for(profile).Glyphs
    integer = type(value) is int if profile == "glyphs2" else isinstance(value, int)
    unicode_lookup = lookup == "glyphInfoForUnicode" or integer
    target = (
        shared
        if lookup == "glyphInfoForName" and integer and profile != "glyphs4"
        else local
    )
    result = getattr(app, lookup)(value, font)
    assert result is target.result, "Return the selected manager result without copying"
    actual = target.calls[-1]
    assert actual[0] == ("unicode" if unicode_lookup else "name")
    if integer:
        expected = (
            "OWNED_04X"
            if profile == "glyphs4" and isinstance(value, FormattedInt)
            else f"{int.__index__(value):04X}"
        )
        assert actual[1] == expected, (
            "Preserve exact conversion spelling without scalar validation"
        )
    else:
        assert actual[1] is value, "Nonintegers reach the manager unchanged"
    other = local if target is shared else shared
    assert not other.calls, "Only the source-selected manager receives a lookup"
    assert font.reads == (target is local), "Font access matches the source routing"


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("lookup", ("glyphInfoForName", "glyphInfoForUnicode"))
def test_omitted_font_when_lookup_then_shared_without_active_font(
    profile, lookup, managers
):
    shared, local, font = managers
    result = getattr(module_for(profile).Glyphs, lookup)(65)
    assert result is shared.result
    assert shared.calls == [("unicode", "0041")]
    assert not local.calls and font.reads == 0


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("lookup", ("glyphInfoForName", "glyphInfoForUnicode"))
def test_format_failure_when_integer_subclass_then_versioned_order(
    profile, lookup, managers
):
    app = module_for(profile).Glyphs
    value = RaisingInt(65)
    if profile == "glyphs4":
        with pytest.raises(ValueError, match="owned-format-error"):
            getattr(app, lookup)(value, Forbidden())
        assert not managers[0].calls and not managers[1].calls
    else:
        target = (
            managers[0]
            if profile == "glyphs3" and lookup == "glyphInfoForName"
            else managers[1]
        )
        assert getattr(app, lookup)(value, managers[2]) is target.result
        if profile == "glyphs2":
            assert target.calls[-1][1] is value
        else:
            assert target.calls[-1][1] == "0041"


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("font_given", (False, True))
@pytest.mark.parametrize("override_kind", ("instance", "subclass"))
def test_integer_name_when_unicode_overridden_then_exact_forwarding(
    profile, font_given, override_kind, managers
):
    app = module_for(profile).Glyphs
    calls, result = [], object()

    def override(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    if override_kind == "instance":
        object.__setattr__(app, "glyphInfoForUnicode", override)
    else:

        class Custom(type(app)):
            def glyphInfoForUnicode(self, *args, **kwargs):
                return override(*args, **kwargs)

        app = Custom(Forbidden(), Forbidden(), {}, None, print)
    font = managers[2] if font_given else None
    assert app.glyphInfoForName(65, font) is result
    assert calls == [((65,), {"font": font} if profile == "glyphs4" else {})]
    assert not managers[0].calls and not managers[1].calls


def test_direct_construction_when_profile_absent_then_actual_glyphs4(managers):
    app = GSApplication(Forbidden(), Forbidden(), {}, None, print)
    assert app.glyphInfoForUnicode(string_or_int=FormattedInt(65)) is managers[0].result
    assert managers[0].calls == [("unicode", "OWNED_04X")]
    assert app.glyphInfoForName(65, managers[2]) is managers[1].result


@pytest.mark.parametrize("profile", PROFILES)
def test_provider_when_profile_selected_then_fresh_modules_without_leakage(
    profile, managers
):
    provider = glyphsapp_provider(
        Forbidden(), Forbidden(), profile=profile, error_sink=print
    )
    first, second = provider(), provider()
    assert first is not second and first.Glyphs is not second.Glyphs
    before = inspect.signature(first.Glyphs.glyphInfoForUnicode)
    module_for("glyphs4" if profile != "glyphs4" else "glyphs2")
    assert inspect.signature(first.Glyphs.glyphInfoForUnicode) == before
    expected = "string_or_int" if profile == "glyphs4" else "String"
    assert first.Glyphs.glyphInfoForUnicode(**{expected: "0041"}) is managers[0].result


@pytest.mark.parametrize("profile", ("auto", "glyphs1", "Glyphs4", "", None, 4, []))
@pytest.mark.parametrize("factory", (make_glyphsapp_module, glyphsapp_provider))
def test_factory_when_ambiguous_or_invalid_profile_then_rejected(profile, factory):
    with pytest.raises(ValueError, match="profile"):
        factory(Forbidden(), Forbidden(), profile=profile, error_sink=print)


@pytest.mark.parametrize("profile", PROFILES)
def test_session_adapters_when_context_profile_selected_then_facade_matches(
    profile, tmp_path
):
    from fontlab_glyport.glyphsapp.fontlab_session import FontLabSession

    ctx = ExecutionContext(tmp_path, profile)
    session = object.__new__(FontLabSession)
    session.ctx, session.model, session.bridge = ctx, Forbidden(), Forbidden()
    session.defaults, session._menu, session._filters = {}, object(), {}
    module = session.adapters()["GlyphsApp"]()
    expected = "string_or_int" if profile == "glyphs4" else "String"
    assert (
        str(inspect.signature(module.Glyphs.glyphInfoForUnicode))
        == f"({expected}, font=None)"
    )
    name = "String" if profile == "glyphs2" else "name"
    assert (
        str(inspect.signature(module.Glyphs.glyphInfoForName)) == f"({name}, font=None)"
    )
    ctx.close()


@pytest.mark.parametrize("profile", PROFILES)
def test_bridge_provider_when_context_profile_selected_then_facade_matches(
    profile, tmp_path, monkeypatch
):
    from fontlab_glyport.glyphsapp import fontlab_bridge

    class Bridge:
        def __init__(self, **kwargs):
            self.closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr(fontlab_bridge, "FontLabBackend", lambda packages: Forbidden())
    monkeypatch.setattr(fontlab_bridge, "Model", lambda backend: Forbidden())
    monkeypatch.setattr(fontlab_bridge, "FontLabGlyphsBridge", Bridge)
    ctx = ExecutionContext(tmp_path, profile)
    provider = fontlab_bridge.fontlab_glyphsapp_provider(
        ctx, version=(99, 999), packages=[], defaults={}
    )
    app = provider().Glyphs
    expected = "String" if profile == "glyphs2" else "name"
    assert str(inspect.signature(app.glyphInfoForName)) == f"({expected}, font=None)"
    expected = "string_or_int" if profile == "glyphs4" else "String"
    assert str(inspect.signature(app.glyphInfoForUnicode)) == f"({expected}, font=None)"
    ctx.close()
    assert app._bridge.closed


def test_auto_execution_when_unresolved_then_provider_receives_resolved_glyphs4(
    tmp_path,
):
    from fontlab_glyport import run_script
    from fontlab_glyport.entrypoints import ExecutionHost, ExecutionOptions
    from fontlab_glyport.receipt import ReceiptEnvironment

    seen = []

    def adapters(ctx, font):
        seen.append(ctx.profile)
        return {
            "GlyphsApp": glyphsapp_provider(
                Forbidden(), Forbidden(), profile=ctx.profile, error_sink=print
            )
        }

    host = ExecutionHost(
        lambda operation: operation(),
        ReceiptEnvironment("owned", "1", "3.11", None, "owned", "owned"),
        adapter_factory=adapters,
    )
    script = tmp_path / "main.py"
    script.write_text("value = 42\n")
    handle = run_script(script, host=host, options=ExecutionOptions(cocoa_backend="qt"))
    try:
        assert seen == ["glyphs4"], (
            "The execution layer resolves auto before facade selection"
        )
        app = handle.context.adapters["GlyphsApp"]().Glyphs
        assert (
            str(inspect.signature(app.glyphInfoForUnicode))
            == "(string_or_int, font=None)"
        )
        assert any(
            item.code == "PROFILE_RUNTIME_DEFAULT"
            for item in handle.receipt.diagnostics
        )
    finally:
        handle.close()


@pytest.mark.parametrize("profile", PROFILES)
def test_name_integer_when_font_unreadable_then_only_glyphs4_accesses_font(
    profile, managers
):
    app = module_for(profile).Glyphs
    if profile == "glyphs4":
        with pytest.raises(AssertionError, match="No implicit font"):
            app.glyphInfoForName(65, Forbidden())
        assert not managers[0].calls
    else:
        assert app.glyphInfoForName(65, Forbidden()) is managers[0].result
        assert managers[0].calls == [("unicode", "0041")]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("lookup", ("glyphInfoForName", "glyphInfoForUnicode"))
def test_false_font_and_nil_result_when_explicit_then_no_fallback(
    profile, lookup, managers
):
    class FalseFont(Font):
        def __bool__(self):
            return False

    managers[1].result = None
    font = FalseFont(managers[1])
    result = getattr(module_for(profile).Glyphs, lookup)("0041", font=font)
    assert result is None, "The selected manager nil result is returned directly"
    assert font.reads == 1 and not managers[0].calls
    assert managers[1].calls == [
        ("name" if lookup == "glyphInfoForName" else "unicode", "0041")
    ]


@pytest.mark.parametrize("factory", (make_glyphsapp_module, glyphsapp_provider))
def test_factory_when_profile_omitted_then_glyphs4_without_host_reads(
    factory, managers
):
    made = factory(Forbidden(), Forbidden(), error_sink=print)
    module = made() if factory is glyphsapp_provider else made
    assert type(module.Glyphs) is GSApplication
    assert (
        module.Glyphs.glyphInfoForUnicode(string_or_int=FormattedInt(65))
        is managers[0].result
    )
    assert managers[0].calls == [("unicode", "OWNED_04X")]
    assert (
        inspect.signature(factory).parameters["profile"].kind
        is inspect.Parameter.KEYWORD_ONLY
    )
