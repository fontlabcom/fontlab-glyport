# this_file: tests/test_errors.py
"""Typed failures serialize original context and never intercept process exits."""

import subprocess
import sys
from dataclasses import replace

import pytest

import fontlab_glyport as glyport


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("GlyportError", "GLYPORT_ERROR"),
        ("HostUnavailable", "HOST_UNAVAILABLE"),
        ("UnsupportedCapability", "UNSUPPORTED_CAPABILITY"),
        ("AdaptationError", "ADAPTATION_ERROR"),
        ("DependencyUnavailable", "DEPENDENCY_UNAVAILABLE"),
        ("StaleNativeObject", "STALE_NATIVE_OBJECT"),
        ("NativeOperationError", "NATIVE_OPERATION_ERROR"),
        ("Cancelled", "CANCELLED"),
        ("PartialFailure", "PARTIAL_FAILURE"),
    ],
)
def test_error_when_rendered_then_retains_code_original_location_and_recovery(
    receipt, name, code
):
    error_type = getattr(glyport, name)
    location = glyport.SourceLocation("src/original.py", 7, 3)
    error = error_type(
        "Operation failed",
        location=location,
        capability="glyphs:model",
        recovery_action="Retry in the host",
    )
    assert isinstance(error, glyport.GlyportError)
    assert isinstance(error, Exception)
    assert error.code == code
    assert str(error) == "Operation failed"
    diagnostic = error.to_diagnostic()
    assert isinstance(diagnostic, glyport.ReceiptDiagnostic)
    assert diagnostic.to_dict() == {
        "code": code,
        "severity": "error",
        "message": "Operation failed",
        "location": {"path": "src/original.py", "line": 7, "column": 3},
        "capability": "glyphs:model",
        "recovery_action": "Retry in the host",
        "field": None,
    }
    assert (
        glyport.validate_receipt(replace(receipt, diagnostics=(diagnostic,)).to_dict())
        == []
    )


def test_error_when_context_unavailable_then_records_nulls():
    diagnostic = glyport.HostUnavailable("FontLab is unavailable").to_diagnostic()
    assert diagnostic.location is None
    assert diagnostic.capability is None
    assert diagnostic.recovery_action is None


@pytest.mark.parametrize("exit_type", [SystemExit, KeyboardInterrupt])
def test_error_when_process_control_raised_then_glyport_handler_does_not_catch(
    exit_type,
):
    with pytest.raises(exit_type):
        try:
            raise exit_type()
        except glyport.GlyportError:
            pytest.fail("process control was swallowed by GlyportError")


def test_import_when_host_and_ui_imports_forbidden_then_public_api_still_loads():
    script = """
import importlib.abc
import sys

blocked = {"fontlab", "fontgate", "fontpr", "fontlabpr", "PythonQt", "PySide2",
           "PySide6", "PyQt5", "PyQt6", "GlyphsApp", "vanilla", "AppKit",
           "Foundation", "Cocoa", "objc", "fontlabapp", "pythonqtside"}

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise AssertionError("native import attempted: " + fullname)

sys.meta_path.insert(0, Guard())
import fontlab_glyport
from fontlab_glyport import *
assert "Receipt" in fontlab_glyport.__all__
assert not blocked.intersection(sys.modules)
assert fontlab_glyport.Diagnostic.__module__ == "fontlab_glyport.assessment"
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_partial_failure_when_bare_then_errors_is_empty_tuple():
    from fontlab_glyport.errors import PartialFailure

    assert PartialFailure("x").errors == (), "errors must be a declared default"
