# this_file: tests/test_fontlab_model_backend.py
"""Only import safety and pure mapping checks; no native execution claimed."""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from fontlab_glyport.model.fontlab_backend import NODE_TYPE_MAPPING, node_type


def _node(kind):
    """Native flags (glyport-matrix probe_nodes): "off" quadratic off-curve,
    "curve" cubic control point, "on" on-curve."""
    return SimpleNamespace(isOff=lambda: kind == "off", isCurve=lambda: kind == "curve")


@pytest.mark.parametrize(
    "kind,previous,quadratic,expected",
    [
        ("off", "on", True, "offcurve"),
        ("curve", "on", False, "offcurve"),
        ("on", None, False, "line"),
        ("on", "on", False, "line"),
        ("on", "curve", False, "curve"),
        ("on", "off", True, "qcurve"),
    ],
)
def test_native_flag_mapping(kind, previous, quadratic, expected):
    before = None if previous is None else _node(previous)
    assert node_type(_node(kind), quadratic, before) == expected
    assert set(NODE_TYPE_MAPPING.values()) == {"line", "curve", "offcurve", "qcurve"}


def test_imports_and_construction_never_load_native_modules():
    code = """
import sys
class RejectNative:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'fontlab', 'fontgate', 'PySide2', 'PythonQt'}:
            raise AssertionError('native import attempted: ' + fullname)
sys.meta_path.insert(0, RejectNative())
import fontlab_glyport
import fontlab_glyport.model
from fontlab_glyport.model.fontlab_backend import FontLabBackend, owned_test_package
FontLabBackend()
FontLabBackend(packages=[])
assert not {'fontlab', 'fontgate', 'PySide2', 'PythonQt'} & sys.modules.keys()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
