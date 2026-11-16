# this_file: tests/test_issue106_bundle.py
"""Owned temporary bundle fixtures exercise resource lookup without Cocoa."""

import plistlib
import sys
from types import ModuleType

import pytest
from ui_doubles_session import make_session

from fontlab_glyport.errors import (
    NativeOperationError,
    UnsupportedAttribute,
    UnsupportedCapability,
)


@pytest.fixture
def bundle(tmp_path):
    from fontlab_glyport.bundles import bundle_class

    root = tmp_path / "Example.glyphsPlugin"
    resources = root / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (root / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": "org.example.fixture",
                "CFBundleName": "Example",
                "Nested": {"value": 1},
            }
        )
    )
    (resources / "icon.txt").write_text("fixture")
    return root, resources, bundle_class(resources)


def test_bundle_when_path_and_resources_then_returns_paths_and_missing_is_none(bundle):
    root, resources, cls = bundle
    value = cls.bundleWithPath_(str(root))
    assert value.bundlePath() == str(root)
    assert value.resourcePath() == str(resources)
    assert value.pathForResource_ofType_("icon", "txt") == str(resources / "icon.txt")
    assert value.pathForResource_ofType_("icon.txt", None) == str(
        resources / "icon.txt"
    )
    assert value.pathForResource_ofType_("missing", "txt") is None
    assert cls.bundleWithPath_(str(root / "missing")) is None
    assert cls.bundleWithPath_(str(resources / "icon.txt")) is None
    assert value.bundleIdentifier() == "org.example.fixture"
    assert cls.bundleWithIdentifier_("org.example.fixture").bundlePath() == str(root)
    assert cls.bundleWithIdentifier_("org.example.missing") is None


def test_bundle_when_flat_bundle_and_subdirectory_then_resource_lookup(tmp_path):
    from fontlab_glyport.bundles import bundle_class

    root = tmp_path / "Flat.bundle"
    (root / "Resources" / "data").mkdir(parents=True)
    item = root / "Resources" / "data" / "sample.json"
    item.write_text("{}")
    value = bundle_class(root).bundleWithPath_(root)
    assert value.pathForResource_ofType_inDirectory_("sample", "json", "data") == str(
        item
    )


def test_bundle_when_class_in_owned_module_then_finds_enclosing_bundle(
    bundle, monkeypatch
):
    root, resources, cls = bundle
    module = ModuleType("fixture_plugin")
    module.__file__ = str(resources / "plugin.py")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    plugin = type("ExamplePlugin", (), {"__module__": module.__name__})
    assert cls.bundleForClass_(plugin).bundlePath() == str(root)
    with pytest.raises(UnsupportedCapability) as error:
        cls.bundleForClass_(str)
    assert error.value.capability == "NSBundle.bundleForClass_"


def test_bundle_when_info_returned_then_dictionary_supports_cocoa_and_copy_isolation(
    bundle,
):
    root, _, cls = bundle
    value = cls.bundleWithPath_(root)
    info = value.infoDictionary()
    assert info.objectForKey_("CFBundleName") == "Example"
    assert info.objectForKey_("absent") is None
    info["Nested"]["value"] = 2
    assert value.infoDictionary()["Nested"]["value"] == 1
    (root / "Contents" / "Info.plist").write_bytes(b"bad plist")
    with pytest.raises(NativeOperationError) as error:
        value.infoDictionary()
    assert error.value.capability == "NSBundle.infoDictionary"


@pytest.mark.parametrize(
    "payload",
    [b"<plist><dict>", plistlib.dumps(["not a dictionary"])],
)
def test_bundle_when_invalid_metadata_then_typed_error(bundle, payload):
    root, _, cls = bundle
    (root / "Contents" / "Info.plist").write_bytes(payload)
    with pytest.raises(NativeOperationError) as error:
        cls.bundleWithPath_(root).infoDictionary()
    assert error.value.capability == "NSBundle.infoDictionary"


@pytest.mark.parametrize("member", ["mainBundle", "load", "loadNibNamed_owner_"])
def test_bundle_when_native_loading_requested_then_precise_unsupported(bundle, member):
    root, _, cls = bundle
    target = cls if member == "mainBundle" else cls.bundleWithPath_(root)
    with pytest.raises(UnsupportedCapability) as error:
        getattr(target, member)()
    assert error.value.capability == f"NSBundle.{member}"
    assert error.value.location.path == __file__


def test_bundle_when_script_imports_any_cocoa_alias_then_session_exposes_same_class(
    bundle, tmp_path
):
    _, resources, _ = bundle
    ctx, _ = make_session(resources)
    script = resources / "probe.py"
    script.write_text(
        "from Foundation import NSBundle\n"
        "from AppKit import NSBundle as OtherBundle, NSAffineTransformStruct\n"
        "from Cocoa import NSBundle as ThirdBundle\n"
        "class Plugin: pass\n"
        "same = NSBundle is OtherBundle is ThirdBundle\n"
        "path = NSBundle.bundleForClass_(Plugin).resourcePath()\n"
    )
    ctx.run(script)
    assert ctx.globals["same"]
    assert ctx.globals["path"] == str(resources)
    ctx.close()


def test_bundle_when_unknown_member_then_feature_probes_work(bundle):
    root, _, cls = bundle
    for target in (cls, cls.bundleWithPath_(root)):
        assert not hasattr(target, "missingMember")
        assert getattr(target, "missingMember", 42) == 42
        with pytest.raises(UnsupportedAttribute) as error:
            _ = target.missingMember
        assert error.value.capability == "NSBundle.missingMember"
    assert (
        cls.bundleWithPath_(root).objectForInfoDictionaryKey_("CFBundleName")
        == "Example"
    )
    assert cls.bundleWithPath_(root).objectForInfoDictionaryKey_("missing") is None


@pytest.mark.parametrize("directory", ["/tmp", "../../../", "../../../outside"])
def test_bundle_when_directory_escapes_then_rejected(bundle, directory):
    root, _, cls = bundle
    with pytest.raises(ValueError):
        cls.bundleWithPath_(root).pathForResource_ofType_inDirectory_(
            "x", None, directory
        )


def test_bundle_when_resource_symlink_escapes_then_rejected(bundle, tmp_path):
    root, resources, cls = bundle
    (tmp_path / "outside.txt").write_text("outside")
    (resources / "link.txt").symlink_to(tmp_path / "outside.txt")
    with pytest.raises(ValueError):
        cls.bundleWithPath_(root).pathForResource_ofType_("link", "txt")


def test_bundle_when_extension_case_differs_then_enclosing_bundle_found(
    tmp_path, monkeypatch
):
    from fontlab_glyport.bundles import bundle_class

    root = tmp_path / "Mixed.GLYPHSPLUGIN"
    root.mkdir()
    module = ModuleType("mixed_plugin")
    module.__file__ = str(root / "plugin.py")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    plugin = type("Plugin", (), {"__module__": module.__name__})
    assert bundle_class(root).bundleForClass_(plugin).bundlePath() == str(root)
