# this_file: tests/test_profiles_runtime.py
"""Profile evidence is conservative and overrides remain inspectable."""

import plistlib

import pytest

from fontlab_glyport import inspect_source
from fontlab_glyport.profiles import select_profile


def test_python2_syntax_selects_legacy_era_with_diagnostic():
    result = select_profile(sources={"legacy.py": b"print 'legacy'\n"})
    assert result.profile == "glyphs2"
    assert any(d.code == "PROFILE_LEGACY_SYNTAX" for d in result.diagnostics)


@pytest.mark.parametrize("major", [2, 3, 4])
def test_declared_profile_and_override(major):
    assert (
        select_profile(metadata={"GlyphsVersion": str(major)}).profile
        == f"glyphs{major}"
    )
    result = select_profile(metadata={"GlyphsVersion": str(major)}, override="glyphs3")
    assert result.profile == "glyphs3"
    assert any(d.code == "PROFILE_OVERRIDE" for d in result.diagnostics)


def test_ambiguous_and_conflicting_evidence():
    assert (
        select_profile(sources={"a.py": b"from GlyphsApp import Glyphs\n"}).profile
        == "auto"
    )
    result = select_profile(
        metadata={"GlyphsVersion": "4"}, sources={"a.py": b"# GLYPHS_VERSION: 2\n"}
    )
    assert result.profile == "auto"
    assert any(d.code == "PROFILE_AMBIGUOUS" for d in result.diagnostics)


def test_api_usage_is_minimum_not_exact_generation():
    result = select_profile(
        sources={"a.py": b"from GlyphsApp import GSMetric\nlayer.shapes.append(path)\n"}
    )
    assert result.profile == "glyphs3"
    assert any(d.code == "PROFILE_MINIMUM" for d in result.diagnostics)
    assert (
        select_profile(sources={"a.py": b"text = 'layer.shapes'\n"}).profile == "auto"
    )


def test_bundle_metadata_without_execution(tmp_path):
    bundle = tmp_path / "Test.glyphsPlugin"
    (bundle / "Contents/Resources").mkdir(parents=True)
    (bundle / "Contents/Info.plist").write_bytes(
        plistlib.dumps({"GlyphsVersion": "4", "PyMainFileNames": ["plugin.py"]})
    )
    (bundle / "Contents/Resources/plugin.py").write_text(
        "raise AssertionError('never execute')\n"
    )
    assert inspect_source(bundle).profile == "glyphs4"


def test_guard_uses_reference_profile_and_build_is_not_major():
    result = select_profile(
        sources={"a.py": b"if Glyphs.versionNumber >= 3:\n pass\nelse:\n pass\n"}
    )
    assert result.profile == "glyphs4"
    assert any(d.code == "PROFILE_VERSION_GUARD" for d in result.diagnostics)
    assert (
        select_profile(
            metadata={"CFBundleVersion": "4", "GSMinVersion": "3000"}
        ).profile
        == "auto"
    )
