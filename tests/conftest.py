# this_file: tests/conftest.py
"""Complete receipt fixtures keep validation tests independent of native hosts."""

import pytest
from info_edit_fixtures import (
    owned_composition_info as owned_composition_info,  # noqa: PLC0414 - register shared pytest fixture
)
from info_edit_fixtures import (
    owned_edit_info as owned_edit_info,  # noqa: PLC0414 - register shared pytest fixture
)

from fontlab_glyport import (
    Adaptation,
    Artifact,
    Capability,
    Receipt,
    ReceiptAdapter,
    ReceiptDiagnostic,
    ReceiptEnvironment,
    ReceiptSource,
    SourceLocation,
    SourceMap,
    Stage,
)


@pytest.fixture
def receipt():
    """Describe synthetic execution evidence without claiming a native run."""
    return Receipt(
        run_id="fixture-run",
        source=ReceiptSource(
            "example/project",
            "revision-1",
            "src/café.py",
            "a" * 64,
            {"src/café.py": "b" * 64},
        ),
        environment=ReceiptEnvironment(
            "fixture-host",
            "fixture-build",
            "3.11.6",
            "fixture-qt",
            "fixture-os",
            "fixture-arch",
        ),
        adapter=ReceiptAdapter("0.1", "glyphs3", "1"),
        adaptations=(
            Adaptation(
                "syntax-1",
                "Translate legacy syntax",
                "a" * 64,
                "b" * 64,
                SourceMap("maps/syntax.json", "c" * 64),
            ),
        ),
        capabilities=(Capability("glyphs:model", "passed", ("fixture:model",)),),
        stages=(
            Stage(
                "execute",
                "passed",
                "2026-10-14T10:00:00Z",
                "2026-10-14T10:00:01.123Z",
                ("fixture:execution",),
            ),
        ),
        artifacts=(Artifact("font", "artifacts/output.otf", "d" * 64),),
        diagnostics=(
            ReceiptDiagnostic(
                "FIXTURE_ONLY",
                "info",
                "Synthetic café fixture; no native assertion",
                SourceLocation("src/café.py", 1, 1),
                "glyphs:model",
                "Run native assertions before claiming compatibility",
            ),
        ),
    )


@pytest.fixture(autouse=True)
def _isolated_glyphs_defaults(monkeypatch, tmp_path):
    """Persisted Glyphs.defaults never reach the real home folder in tests."""
    monkeypatch.setenv("GLYPORT_DEFAULTS", str(tmp_path / "glyport-defaults.json"))


@pytest.fixture
def cocoa_modules(monkeypatch):
    """Inject bridge metadata/runtime doubles, never native acceptance evidence."""
    import sys
    from importlib.machinery import ExtensionFileLoader, ModuleSpec
    from types import ModuleType

    def install(
        base="/scratch/.local/glyport-80-native",
        roots=("objc", "Foundation", "AppKit", "Cocoa"),
    ):
        modules = {}
        classes = {name: type(name, (), {}) for name in ("NSObject", "NSColor")}
        extension = ModuleType("objc._objc")
        extension.__file__ = base + "/objc/_objc.so"
        extension.__spec__ = ModuleSpec(
            "objc._objc", ExtensionFileLoader("objc._objc", extension.__file__)
        )
        extension.objc_class = type
        extension.lookUpClass = classes.__getitem__
        monkeypatch.setitem(sys.modules, "objc._objc", extension)
        for name in roots:
            module = modules[name] = ModuleType(name)
            module.__file__ = f"{base}/{name}/__init__.py"
            module.__path__ = [f"{base}/{name}"]
            if name == "objc":
                module.objc_class = extension.objc_class
                module.lookUpClass = extension.lookUpClass
            else:

                def lookup(key, values=classes):
                    if key in values:
                        return values[key]
                    raise AttributeError(key)

                lookup.__module__ = "objc._lazyimport"
                module.__getattr__ = lookup
            monkeypatch.setitem(sys.modules, name, module)
        return modules

    return install


@pytest.fixture
def owned_info_manager(tmp_path):
    """Parse independent owned rows; never qualify public resource omissions.

    Fresh custom records have source-established nil/zero group defaults. This
    private fixture seam does not implement the public local initializer.
    """
    from xml.sax.saxutils import quoteattr

    from fontlab_glyport.glyphsapp import GSGlyphsInfo
    from fontlab_glyport.model.custom_info_loading import load_custom_file
    from fontlab_glyport.model.info_records import GlyphInfoIndex

    sequence = 0

    def install(rows=None):
        nonlocal sequence
        if rows is None:
            rows = [
                {
                    "name": "A",
                    "unicode": "0041",
                    "category": "Letter",
                    "case": "upper",
                    "script": "latin",
                },
                {
                    "name": "a",
                    "unicode": "0061",
                    "category": "Letter",
                    "case": "lower",
                    "script": "latin",
                },
                {
                    "name": "acutecomb",
                    "unicode": "0301",
                    "category": "Mark",
                    "subCategory": "Nonspacing",
                },
                {
                    "name": "one",
                    "unicode": "0031",
                    "category": "Number",
                    "subCategory": "Decimal Digit",
                },
            ]
        entries = []
        for row in rows:
            fields = {"direction": "LTR", "decompose": "", **row}
            attributes = " ".join(
                f"{key}={quoteattr(value)}" for key, value in fields.items()
            )
            entries.append(f"<glyph {attributes}/>")
        sequence += 1
        path = tmp_path / f"owned-glyphdata-{sequence}.xml"
        path.write_text(
            "<glyphData>" + "".join(entries) + "</glyphData>", encoding="utf-8"
        )
        index = GlyphInfoIndex()
        assert load_custom_file(index, path) is None, (
            "Owned fixture must parse through real loader"
        )
        return GSGlyphsInfo._from_index(index)

    return install
