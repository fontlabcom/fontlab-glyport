# this_file: tests/test_inspection.py
"""Inspection is read-only, deterministic, and makes no native success claims."""

import hashlib
import json
import plistlib
import subprocess
import sys

import pytest

from fontlab_glyport import inspect_source


def test_script_when_inspected_then_not_executed_and_hash_preserved(tmp_path):
    source = tmp_path / "Original.py"
    source.write_text("from GlyphsApp import Glyphs\nraise RuntimeError('executed')\n")
    original = source.read_bytes()
    assessment = inspect_source(source)
    assert source.read_bytes() == original, "inspection changed original source"
    assert assessment.source_id == hashlib.sha256(original).hexdigest()
    assert assessment.entrypoints == ("Original.py",)
    assert "glyphs:model" in assessment.required_capabilities
    assert assessment.profile == "auto", "auto must not invent a detected version"
    assert assessment.to_dict()["runtime_status"] == "unexecuted"


def test_bundle_when_inspected_then_alias_protocol_and_resources_recorded(tmp_path):
    bundle = tmp_path / "Example.glyphsReporter"
    resources = bundle / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (bundle / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps(
            {"NSPrincipalClass": "Example", "PyMainFileNames": ["plugin.py"]}
        )
    )
    (resources / "plugin.py").write_text(
        "from GlyphsApp.plugins import ReporterPlugin as Base\n"
        "from vanilla import Window\nclass Example(Base):\n    pass\n"
    )
    (resources / "dialog.xib").write_text("<document/>")
    assessment = inspect_source(bundle, profile="glyphs3")
    assert assessment.profile == "glyphs3"
    assert assessment.entrypoints == ("Contents/Resources/plugin.py",)
    assert {"glyphs:ReporterPlugin", "ui:vanilla", "ui:xib"} <= set(
        assessment.required_capabilities
    )
    assert assessment.to_dict()["principal_class"] == "Example"
    assert inspect_source(bundle).source_id == inspect_source(bundle).source_id


def test_bundle_when_native_only_then_retains_binary_and_required_route(tmp_path):
    bundle = tmp_path / "Native.glyphsPlugin"
    native = bundle / "Contents" / "MacOS"
    native.mkdir(parents=True)
    (native / "plugin").write_bytes(bytes.fromhex("cffaedfe") + b"fixture")
    assessment = inspect_source(bundle)
    assert assessment.entrypoints == ()
    assert "native:mach-o" in assessment.required_capabilities
    assert "native:bundle" in assessment.required_capabilities
    assert any(d.code == "NATIVE_ROUTE_REQUIRED" for d in assessment.diagnostics)


def test_python_when_legacy_syntax_then_error_reported_without_adaptation(tmp_path):
    source = tmp_path / "Legacy.py"
    source.write_text("print 'legacy'\n")
    assessment = inspect_source(source)
    diagnostic = next(
        d for d in assessment.diagnostics if d.code == "PYTHON_PARSE_ERROR"
    )
    assert diagnostic.line == 1
    assert assessment.adaptations == (), "inspection must not claim a transformation"


def test_python_when_non_utf8_then_pep263_encoding_read(tmp_path):
    source = tmp_path / "Encoded.py"
    source.write_bytes(b"# coding: latin-1\nname = 'caf\xe9'\n")
    assessment = inspect_source(source)
    assert not any(d.code == "PYTHON_PARSE_ERROR" for d in assessment.diagnostics)


def test_bundle_when_external_symlink_then_link_recorded_not_followed(tmp_path):
    external = tmp_path / "outside.py"
    external.write_text("raise RuntimeError('not part of bundle')\n")
    bundle = tmp_path / "Links.glyphsPlugin"
    bundle.mkdir()
    (bundle / "linked.py").symlink_to(external)
    assessment = inspect_source(bundle)
    file = assessment.to_dict()["files"][0]
    assert file["kind"] == "symlink"
    assert file["sha256"] is None, (
        "link target bytes must not be presented as bundled bytes"
    )
    assert any(d.code == "SYMLINK_UNRESOLVED" for d in assessment.diagnostics)


def test_dependency_when_relative_and_dynamic_then_limits_visible(tmp_path):
    source = tmp_path / "Imports.py"
    source.write_text(
        "from .helpers import utility\nimport importlib\nimportlib.import_module(name)\n"
    )
    assessment = inspect_source(source)
    assert any(d.module == ".helpers" for d in assessment.dependencies)
    assert any(d.code == "DYNAMIC_IMPORT" for d in assessment.diagnostics)
    assert any(d.code == "STATIC_INSPECTION_ONLY" for d in assessment.diagnostics)


@pytest.mark.parametrize("profile", ["glyphs1", "", None])
def test_profile_when_unknown_then_rejected(tmp_path, profile):
    source = tmp_path / "Original.py"
    source.write_text("")
    with pytest.raises(ValueError, match="profile"):
        inspect_source(source, profile=profile)


def test_input_when_missing_or_not_supported_then_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        inspect_source(tmp_path / "missing.py")
    with pytest.raises(ValueError, match="script or Glyphs bundle"):
        inspect_source(tmp_path)


def test_cli_when_parse_error_then_json_written_and_nonzero(tmp_path):
    source = tmp_path / "Bad.py"
    source.write_text("print 'old'\n")
    output = tmp_path / "assessment.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fontlab_glyport",
            "inspect",
            str(source),
            "--json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert json.loads(output.read_text())["runtime_status"] == "unexecuted"


def test_cli_when_output_is_original_then_rejected_without_overwrite(tmp_path):
    source = tmp_path / "Original.py"
    source.write_text("name = 'preserve me'\n")
    original = source.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fontlab_glyport",
            "inspect",
            str(source),
            "--json",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "CLI must protect its input"
    assert source.read_bytes() == original, "CLI overwrote original source"


def test_cli_when_output_hardlinks_source_then_original_preserved(tmp_path):
    import os

    source = tmp_path / "Original.py"
    source.write_text("name = 'original'\n")
    output = tmp_path / "assessment.json"
    os.link(source, output)
    original = source.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fontlab_glyport",
            "inspect",
            str(source),
            "--json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, "CLI must reject an existing output"
    assert source.read_bytes() == original, (
        "report generation overwrote a hardlinked original"
    )


def test_bundle_when_nib_directory_then_requirement_detected(tmp_path):
    bundle = tmp_path / "Nib.glyphsPalette"
    nib = bundle / "Contents" / "Resources" / "dialog.nib"
    nib.mkdir(parents=True)
    (nib / "keyedobjects.bin").write_bytes(b"fixture")
    assert "ui:nib" in inspect_source(bundle).required_capabilities


def test_bundle_when_malformed_xml_then_diagnostic_not_crash(tmp_path):
    bundle = tmp_path / "Bad.glyphsPlugin"
    (bundle / "Contents").mkdir(parents=True)
    (bundle / "Contents" / "Info.plist").write_text("<plist><dict>")
    assert any(
        d.code == "BUNDLE_PLIST_ERROR" for d in inspect_source(bundle).diagnostics
    )


def test_protocol_when_sdk_wildcard_then_discovered(tmp_path):
    source = tmp_path / "plugin.py"
    source.write_text(
        "from GlyphsApp.plugins import *\nclass Example(FilterWithoutDialog):\n    pass\n"
    )
    assert "glyphs:FilterWithoutDialog" in inspect_source(source).required_capabilities


def test_cli_when_report_inside_bundle_then_all_originals_preserved(tmp_path):
    bundle = tmp_path / "Example.glyphsPlugin"
    bundle.mkdir()
    source = bundle / "plugin.py"
    source.write_text("name = 'original'\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fontlab_glyport",
            "inspect",
            str(bundle),
            "--json",
            str(bundle / "assessment.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert sorted(p.name for p in bundle.iterdir()) == ["plugin.py"]


def test_bundle_when_resource_bytes_change_then_source_identity_changes(tmp_path):
    bundle = tmp_path / "Example.glyphsPlugin"
    bundle.mkdir()
    resource = bundle / "icon.svg"
    resource.write_text("<svg/>")
    before = inspect_source(bundle).source_id
    resource.write_text("<svg><path/></svg>")
    assert inspect_source(bundle).source_id != before, (
        "bundle identity ignored resource bytes"
    )


def test_script_when_wx_imported_then_separate_gui_backend_required(tmp_path):
    source = tmp_path / "AppWX.py"
    source.write_text("from wx import App\nimport wx.lib.scrolledpanel\n")
    assessment = inspect_source(source)
    assert "ui:wx" in assessment.required_capabilities
