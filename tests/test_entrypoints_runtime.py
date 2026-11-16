# this_file: tests/test_entrypoints_runtime.py
"""Public handles separate execution, registration, failure and teardown evidence."""

import plistlib

import pytest

from fontlab_glyport import install_plugin, run_script
from fontlab_glyport.entrypoints import (
    ExecutionHost,
    ExecutionOptions,
    PluginRegistration,
)
from fontlab_glyport.errors import (
    HostUnavailable,
    StaleNativeObject,
    UnsupportedCapability,
)
from fontlab_glyport.receipt import ReceiptEnvironment, validate_receipt


@pytest.fixture
def host():
    return ExecutionHost(
        dispatch=lambda operation: operation(),
        environment=ReceiptEnvironment(
            "fixture", "1", "3.11", "5.15", "fixture", "fixture"
        ),
    )


def test_run_receipt_callback_and_close(tmp_path, host):
    path = tmp_path / "main.py"
    path.write_text(
        "# GLYPHS_VERSION: 3\ndef callback():\n from Cocoa import NSMakePoint\n return NSMakePoint(3,4).y\n"
    )
    handle = run_script(path, host=host)
    assert handle.state == "active"
    assert handle.wrap(handle.context.globals["callback"])() == 4
    assert handle.receipt.adapter.profile == "glyphs3"
    assert validate_receipt(handle.receipt.to_dict(), public=False) == []
    before = handle.receipt
    handle.close()
    handle.close()
    assert handle.state == "closed"
    assert before.stages[-1].name == "execution"
    assert handle.receipt.stages[-1].name == "close"


def test_legacy_auto_run_receipt_keeps_transformation_after_close(tmp_path, host):
    path = tmp_path / "legacy.py"
    path.write_text("print 'legacy'\n")
    handle = run_script(path, host=host)
    assert handle.receipt.adapter.profile == "glyphs2"
    assert any(a.id == "py2.print_statement" for a in handle.receipt.adaptations)
    before = handle.receipt.adaptations
    handle.close()
    assert handle.receipt.adaptations == before


def test_no_host_and_auto_runtime_default(tmp_path, host):
    path = tmp_path / "main.py"
    path.write_text("value=42\n")
    with pytest.raises(HostUnavailable):
        run_script(path, profile="glyphs3")
    handle = run_script(path, host=host)
    try:
        assert handle.context.globals["value"] == 42
        assert handle.receipt.adapter.profile == "glyphs4"
        assert any(
            d.code == "PROFILE_RUNTIME_DEFAULT" for d in handle.receipt.diagnostics
        )
    finally:
        handle.close()


def test_failure_attaches_handle_and_receipt(tmp_path, host):
    path = tmp_path / "main.py"
    path.write_text("raise ValueError('fixture failure')\n")
    with pytest.raises(ValueError) as caught:
        run_script(path, profile="glyphs4", host=host)
    handle = caught.value.handle
    assert handle.state == "failed"
    assert handle.context._closed
    assert any(s.status == "failed" for s in handle.receipt.stages)
    assert validate_receipt(handle.receipt.to_dict(), public=False) == []


def test_plugin_registration_unload_and_no_false_success(tmp_path, host):
    bundle = tmp_path / "Test.glyphsPlugin"
    resources = bundle / "Contents/Resources"
    resources.mkdir(parents=True)
    (bundle / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {
                "GlyphsVersion": "3",
                "NSPrincipalClass": "Test",
                "PyMainFileNames": ["plugin.py"],
            }
        )
    )
    (resources / "plugin.py").write_text("class Test:\n pass\n")
    with pytest.raises(UnsupportedCapability, match="registration"):
        install_plugin(bundle, host=host)
    calls = []
    loaded = object()
    host.plugin_installer = lambda context, assessment: PluginRegistration(
        lambda: calls.append("unload"),
        evidence=("fixture:hook-attached",),
        plugin=loaded,
    )
    plugin = install_plugin(bundle, host=host)
    assert plugin.state == "active"
    assert plugin.plugin is loaded, "the loaded plugin instance is reachable"
    assert plugin.receipt.stages[-1].name == "registration"
    plugin.unload()
    plugin.unload()
    assert calls == ["unload"]


def test_dispatch_and_font_invalidation(tmp_path, host):
    path = tmp_path / "main.py"
    path.write_text("value = 42\n")
    calls = []
    host.dispatch = lambda operation: (calls.append("dispatch"), operation())[1]
    handle = run_script(path, profile="glyphs3", host=host)
    callback = handle.wrap(lambda: 1)
    handle.invalidate_document()
    assert handle.state == "closed"
    with pytest.raises(StaleNativeObject):
        callback()
    assert len(calls) >= 2


def test_options_are_typed_and_paths_are_explicit(tmp_path, host):
    root = tmp_path / "scripts"
    root.mkdir()
    (root / "main.py").write_text("value = 42\n")
    handle = run_script(
        "main.py",
        profile="glyphs3",
        options=ExecutionOptions(
            source_root=root, receipt_path=tmp_path / "receipt.json"
        ),
        host=host,
    )
    assert handle.context.globals["value"] == 42
    assert (tmp_path / "receipt.json").exists()
    handle.close()
    with pytest.raises(TypeError):
        run_script(root / "main.py", options={}, host=host)


def test_native_option_failure_closes_prepared_context(tmp_path, host, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    path = tmp_path / "main.py"
    path.write_text("ran = True\n")
    with pytest.raises(ImportError, match="macOS") as failure:
        run_script(
            path,
            profile="glyphs4",
            host=host,
            options=ExecutionOptions(cocoa_backend="native"),
        )
    assert failure.value.handle.context._closed
    assert failure.value.handle.state == "failed"
